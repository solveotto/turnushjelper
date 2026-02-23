import os
import re
import logging
import pandas as pd
import json
import app.utils.db_utils as _db_utils
from config import AppConfig

logger = logging.getLogger(__name__)

class DataframeManager():
    def __init__(self, turnus_set_id=None):
        """Initialize with either a specific turnus set or the active one"""
        self.current_turnus_set = None
        self.df = pd.DataFrame()  # Empty dataframe as default
        self.turnus_data = []     # Empty list as default
        self.load_turnus_set(turnus_set_id)
    
    def load_turnus_set(self, turnus_set_id=None):
        """Load a specific turnus set or the active one"""
        
        if turnus_set_id:
            # Load specific turnus set by ID
            all_sets = _db_utils.get_all_turnus_sets()
            turnus_set = next((ts for ts in all_sets if ts['id'] == turnus_set_id), None)
        else:
            # Load the currently active turnus set
            turnus_set = _db_utils.get_active_turnus_set()
        
        if not turnus_set:
            logger.warning("No turnus set found! Using empty data.")
            self.current_turnus_set = None
            self.df = pd.DataFrame()
            self.turnus_data = []
            return False
        
        self.current_turnus_set = turnus_set
        
        try:
            # Use database file paths if available
            if turnus_set.get('turnus_file_path') and turnus_set.get('df_file_path'):
                # Convert database paths to OS-specific paths
                turnus_path = os.path.normpath(turnus_set['turnus_file_path'])
                df_path = os.path.normpath(turnus_set['df_file_path'])
            else:
                # Construct paths based on turnus set identifier
                year_id = turnus_set['year_identifier'].lower()
                turnus_path = os.path.join(AppConfig.turnusfiler_dir, year_id, f'turnuser_{turnus_set["year_identifier"]}.json')
                df_path = os.path.join(AppConfig.turnusfiler_dir, year_id, f'turnus_df_{turnus_set["year_identifier"]}.json')
            
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
            else:
                logger.warning("Turnus file not found: %s", turnus_path)
                self.turnus_data = []

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

        double_shifts_path = os.path.join(AppConfig.turnusfiler_dir, year_id.lower(), f'double_shifts_{year_id.lower()}.json')
        if not os.path.exists(double_shifts_path):
            return turnus_data

        with open(double_shifts_path, 'r') as f:
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