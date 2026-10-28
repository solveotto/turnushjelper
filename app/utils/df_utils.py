import os
import re
import logging
import pandas as pd
import json
from app.services import turnus_service
from config import AppConfig

logger = logging.getLogger(__name__)


def invalidate_turnus_cache(turnus_set_id):
    """Drop cached turnus JSON/stats and kompdag counts for a turnus set.

    Only reaches the worker that handled the request: the cache is
    SimpleCache (per-process) and production runs 2 gunicorn workers. The
    other worker notices on its next request anyway, because both cached
    entries carry a fingerprint of their source files (files_fingerprint)
    and are rebuilt when it changes, so no restart is needed after an import.
    """
    from app.extensions import cache
    cache.delete(f"turnus_data_{turnus_set_id}")
    cache.delete(f"kompdager_{turnus_set_id}")


def files_fingerprint(*paths):
    """(mtime_ns, size) per file, None for a missing one.

    A few stat calls per request, so every worker can tell whether its cached
    copy is still built from the files on disk.
    """
    fingerprint = []
    for path in paths:
        try:
            st = os.stat(path)
            fingerprint.append((st.st_mtime_ns, st.st_size))
        except OSError:
            fingerprint.append(None)
    return tuple(fingerprint)


def double_shifts_path(year_id):
    version = year_id.lower()
    return os.path.join(AppConfig.turnusfiler_dir, version, f"double_shifts_{version}.json")


class DataframeManager():
    def __init__(self, turnus_set_id=None):
        """Initialize with either a specific turnus set or the active one"""
        self.current_turnus_set = None
        self.df = pd.DataFrame()  # Empty dataframe as default
        self.turnus_data = []     # Empty list as default
        self.source_fingerprint = None
        self.load_turnus_set(turnus_set_id)
    
    def load_turnus_set(self, turnus_set_id=None):
        """Load a specific turnus set or the active one"""
        
        if turnus_set_id:
            # Load specific turnus set by ID
            all_sets = turnus_service.get_all_turnus_sets()
            turnus_set = next((ts for ts in all_sets if ts['id'] == turnus_set_id), None)
        else:
            # Load the currently active turnus set
            turnus_set = turnus_service.get_active_turnus_set()
        
        if not turnus_set:
            logger.warning("No turnus set found! Using empty data.")
            self.current_turnus_set = None
            self.df = pd.DataFrame()
            self.turnus_data = []
            return False
        
        self.current_turnus_set = turnus_set

        # Resolve file paths before checking the cache
        year_id = turnus_set['year_identifier'].lower()
        conventional_turnus = os.path.join(AppConfig.turnusfiler_dir, year_id, f'turnus_schedule_{turnus_set["year_identifier"]}.json')
        conventional_df = os.path.join(AppConfig.turnusfiler_dir, year_id, f'turnus_stats_{turnus_set["year_identifier"]}.json')

        if turnus_set.get('turnus_file_path') and turnus_set.get('df_file_path'):
            turnus_path = os.path.normpath(turnus_set['turnus_file_path'])
            df_path = os.path.normpath(turnus_set['df_file_path'])
            # TurnusSet rows store ABSOLUTE paths, so any relocation of the data
            # store leaves them dangling — moving turnusfiler out of app/static
            # (2026-07-29) invalidated every existing row. Fall back to the
            # conventional location rather than serving an empty DataFrame,
            # which is what a stale path silently produced.
            if not os.path.exists(turnus_path) or not os.path.exists(df_path):
                logger.warning(
                    "Stored path for turnus set %s does not exist (%s); "
                    "falling back to %s",
                    turnus_set['year_identifier'], turnus_path, conventional_turnus,
                )
                turnus_path, df_path = conventional_turnus, conventional_df
        else:
            turnus_path, df_path = conventional_turnus, conventional_df

        # Check in-memory cache before hitting disk. The entry is only good
        # while the files it was built from are unchanged.
        from app.extensions import cache
        cache_key = f"turnus_data_{turnus_set['id']}"
        self.source_fingerprint = files_fingerprint(
            turnus_path, df_path, double_shifts_path(turnus_set['year_identifier'])
        )
        cached = cache.get(cache_key)
        if cached is not None and cached[3] == self.source_fingerprint:
            logger.debug("Cache hit for turnus set %s", turnus_set['year_identifier'])
            self.turnus_data, df_dict, self.current_turnus_set, _ = cached
            self.df = pd.DataFrame(df_dict)
            return True

        try:
            # Load dataframe
            if os.path.exists(df_path):
                self.df = pd.read_json(df_path)
            else:
                logger.warning("DataFrame file not found: %s", df_path)
                self.df = pd.DataFrame()

            # Load turnus data
            if os.path.exists(turnus_path):
                with open(turnus_path, 'r') as f:
                    self.turnus_data = json.load(f)
                # Normalize old-format timer keys (R24/R25) to the current schema
                self.turnus_data = self._normalize_timer_fields(self.turnus_data)
                # Apply double shift flags from double_shifts JSON file
                self.turnus_data = self._apply_double_shift_flags(self.turnus_data, turnus_set['year_identifier'])
                # Runtime integrity check — log warnings, keep running
                from app.utils.pdf.scraper_validator import validate_turnus_json
                _valid, _errors = validate_turnus_json(self.turnus_data)
                if not _valid:
                    for err in _errors:
                        logger.warning("Turnus data integrity: %s", err)
            else:
                logger.warning("Turnus file not found: %s", turnus_path)
                self.turnus_data = []

            # Store in cache (DataFrame serialised as dict to avoid pickling issues)
            cache.set(cache_key, (self.turnus_data, self.df.to_dict(), self.current_turnus_set,
                                  self.source_fingerprint))

            return True
        except Exception as e:
            logger.error("Error loading turnus set %s: %s", turnus_set['year_identifier'], e)
            self.df = pd.DataFrame()
            self.turnus_data = []
            return False
    
    def get_current_turnus_info(self):
        """Get information about the currently loaded turnus set"""
        return self.current_turnus_set
    
    def reload_active_set(self):
        """Reload the currently active turnus set (useful after switching sets)"""
        return self.load_turnus_set()
    
    def has_data(self):
        """Check if we have valid data loaded"""
        return not self.df.empty and len(self.turnus_data) > 0

    def _normalize_timer_fields(self, turnus_data):
        """Normalize old-format timer keys to the current schema.

        Older turnus JSON files (R24, R25) stored totals in 'kl_tim_total' /
        'tj_timer_total' and per-week breakdowns in 'kl_tim' / 'tj_timer'
        (dicts).  Current code (R26+) expects 'kl_timer' and 'tj_timer' to be
        plain strings.  This pass promotes the old total fields so the template
        always sees a string (or None) under the canonical keys.
        """
        for turnus_entry in turnus_data:
            for data in turnus_entry.values():
                if not isinstance(data, dict):
                    continue
                if not isinstance(data.get('kl_timer'), str):
                    data['kl_timer'] = data.get('kl_tim_total') or None
                if not isinstance(data.get('tj_timer'), str):
                    data['tj_timer'] = data.get('tj_timer_total') or None
        return turnus_data

    def _apply_double_shift_flags(self, turnus_data, year_id):
        """Apply shift flags based on double_shifts file."""

        path = double_shifts_path(year_id)
        if not os.path.exists(path):
            return turnus_data

        with open(path, 'r') as f:
            shifts_data = json.load(f)

        # Handle new dict structure or old list structure
        if isinstance(shifts_data, dict):
            double_shifts = shifts_data.get('dobbelt_tur', [])
            delt_dagsverk_list = shifts_data.get('delt_dagsverk', [])
        else:
            # Backwards compatibility with old format
            double_shifts = shifts_data
            delt_dagsverk_list = []

        # Build lookup sets for dobbelt tur
        first_shifts = set()
        second_shifts = set()
        for pair in double_shifts:
            first_base = re.match(r'^(\d+)', pair['first_shift'])
            second_base = re.match(r'^(\d+)', pair['second_shift'])
            if first_base:
                first_shifts.add(first_base.group(1))
            if second_base:
                second_shifts.add(second_base.group(1))

        # Build lookup set for delt dagsverk
        delt_dagsverk_shifts = set()
        for shift in delt_dagsverk_list:
            base = re.match(r'^(\d+)', shift)
            if base:
                delt_dagsverk_shifts.add(base.group(1))

        # Apply flags to turnus_data
        for turnus_entry in turnus_data:
            for turnus_name, weeks in turnus_entry.items():
                for week_nr, week_data in weeks.items():
                    if not isinstance(week_data, dict):
                        continue
                    for day_nr, day_data in week_data.items():
                        if not isinstance(day_data, dict) or 'dagsverk' not in day_data:
                            continue

                        dagsverk = day_data.get('dagsverk', '')
                        base_match = re.match(r'^(\d+)', dagsverk)
                        if base_match:
                            base_num = base_match.group(1)
                            day_data['is_consecutive_shift'] = base_num in first_shifts
                            day_data['is_consecutive_receiver'] = base_num in second_shifts
                            day_data['is_delt_dagsverk'] = base_num in delt_dagsverk_shifts
                        else:
                            day_data['is_consecutive_shift'] = False
                            day_data['is_consecutive_receiver'] = False
                            day_data['is_delt_dagsverk'] = False

        return turnus_data