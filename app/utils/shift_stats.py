import sys
import os

# Add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from datetime import time
import pandas as pd
import numpy as np
import json
from config import AppConfig

'''
- Fridays that goes over 2 hours into saturay counts as weekend days.
'''




class Turnus():
    def __init__(self, json_path) -> None:
        self.turnuser_df = self.JsonToDataframe(json_path)
        self.stats_df = pd.DataFrame()


        self.get_shift_stats()

    def JsonToDataframe(self, turnus_json):
        with open(turnus_json, 'r') as f:
            json_data = json.load(f)
        data = []

        for turnus in json_data:
            for turnus_navn, turnus_dict in turnus.items():
                for uke_nr, uke_data in turnus_dict.items():
                    # Skip non-dict entries (e.g., "materiell", "kl_tim_total", "tj_timer_total")
                    if not isinstance(uke_data, dict):
                        continue
                    for dag_nr, dag_data in uke_data.items():
                        # Skip if dag_data is not a dict (e.g., "materiell" field)
                        if not isinstance(dag_data, dict):
                            continue
                        
                        # Skip if dag_data doesn't have required fields
                        if 'tid' not in dag_data:
                            continue
                        
                        # Konverterer tiden til datetime
                        if len(dag_data['tid']) == 2:
                            start_tid = pd.to_datetime(dag_data['tid'][0], format='%H:%M')
                            slutt_tid = pd.to_datetime(dag_data['tid'][1], format='%H:%M')
                        else:
                            start_tid = pd.to_datetime("00:00", format='%H:%M')
                            slutt_tid = pd.to_datetime("00:00", format='%H:%M')
                            
                        
                        new_row = {
                            'turnus' : turnus_navn,
                            'ukedag' : dag_data['ukedag'],
                            'dag_nr': dag_nr,
                            'uke_nr'   : uke_nr,
                            'start' : start_tid,
                            'slutt' : slutt_tid,
                            'dagsverk' : dag_data['dagsverk']
                        }
                        
                        data.append(new_row)
        df = pd.DataFrame(data)
        df.replace('', np.nan, inplace=True)

        return pd.DataFrame(df)
    


    def get_shift_stats(self):
        df_grpby_turnus = self.turnuser_df.groupby('turnus')
        
        for turnus_navn, turnus_df in df_grpby_turnus:

            turuns_df_reset = turnus_df.reset_index()

            EVENING = time(16,0)

            # Adds new stats to dataframe
            shift_cnt = 0
            helgetimer = 0
            helgetimer_dagtid = 0
            helgedager = 0
            natt_helg = 0
            helgetimer_ettermiddag = 0
            tidlig = 0
            before_6 = 0
            afternoon_count = 0
            afternoon_ends_before_20 = 0
            afternons_in_row = 0
            current_kveld_streak = 0
            night_count = 0
            tidlig_6_8 = 0
            tidlig_8_12 = 0
            total_shift_hours = 0
            current_work_streak = 0
            longest_work_streak = 0
            current_off_streak = 0
            longest_off_streak = 0
            prev_was_night = False

            # Day-of-week off-rate tracking
            weekday_map = {
                'Mandag': 'mon', 'Tirsdag': 'tue', 'Onsdag': 'wed',
                'Torsdag': 'thu', 'Fredag': 'fri', 'Lørdag': 'sat', 'Søndag': 'sun',
            }
            weekday_total = {k: 0 for k in weekday_map.values()}
            weekday_off = {k: 0 for k in weekday_map.values()}
            start_times_minutes = []


            for _index, _dagsverk in turuns_df_reset.iterrows():
                is_work_day = _dagsverk['start'] != _dagsverk['slutt'] and _index + 1 < len(turuns_df_reset)

                # Track day-of-week off rates (skip the summary row at the end)
                if _index + 1 < len(turuns_df_reset):
                    day_key = weekday_map.get(_dagsverk['ukedag'])
                    if day_key:
                        weekday_total[day_key] += 1
                        if not is_work_day:
                            weekday_off[day_key] += 1

                if is_work_day:
                    current_work_streak += 1
                    longest_work_streak = max(longest_work_streak, current_work_streak)
                    current_off_streak = 0
                else:
                    if _index + 1 < len(turuns_df_reset):  # Not the summary row
                        if prev_was_night:
                            # Recovery day after night shift — doesn't count as true day off
                            prev_was_night = False
                        else:
                            current_off_streak += 1
                            longest_off_streak = max(longest_off_streak, current_off_streak)
                    current_work_streak = 0
                    current_kveld_streak = 0

                if is_work_day:
                        shift_cnt += 1
                        start = pd.to_datetime(_dagsverk['start'], format='%H:%M')
                        end = pd.to_datetime(_dagsverk['slutt'], format='%H:%M')
                        ukedag = _dagsverk['ukedag']
                        start_times_minutes.append(start.hour * 60 + start.minute)
                        weekend_days = ['Fredag', 'Lørdag', 'Søndag']

                        # Adjust end time if it's on the next day
                        if end < start:
                            end += pd.Timedelta(days=1)

                        total_shift_hours += (end - start).total_seconds() / 3600

                        # Classify night shifts — aligned with shift-classifier.js
                        # Nattevakt: crosses midnight AND ends 04:00+ next day
                        crosses_midnight = end.date() > start.date()
                        is_night = crosses_midnight and end.time() >= time(4, 0)

                        if is_night:
                            night_count += 1
                            if ukedag in weekend_days:
                                natt_helg += 1

                        prev_was_night = is_night

                        ### WEEKENDS ###
                        if ukedag == 'Fredag':
                            fri_17 = start.replace(hour=17, minute=0, second=0)
                            if end > fri_17:
                                helg_start = max(start, fri_17)
                                friday_helg_hours = (end - helg_start).total_seconds() / 3600
                                helgetimer += friday_helg_hours
                                helgetimer_ettermiddag += friday_helg_hours   # always after 17:00 = evening
                                helgedager += 1


                        elif ukedag == 'Lørdag':
                            saturday_hours = (end - start).total_seconds() / 3600
                            helgetimer += saturday_hours
                            helgedager += 1

                            if start.time() >= time(14, 0):
                                helgetimer_ettermiddag += saturday_hours

                            # Counts daytime hours in weekend
                            if start.time() < time(14, 0):
                                helgetimer_dagtid += saturday_hours



                        elif ukedag == 'Søndag':
                            # counts hours from start through Monday 06:00 (weekend window end)
                            if end.day > start.day:
                                mon_6am = start.replace(hour=6, minute=0, second=0) + pd.Timedelta(days=1)
                                helg_end = min(end, mon_6am)
                                sunday_hours = (helg_end - start).total_seconds() / 3600
                                helgetimer += sunday_hours

                                # Counts evening hours
                                if start.time() >= time(14, 0):
                                    helgetimer_ettermiddag += sunday_hours

                            # Counts sunday weekend hours
                            else:
                                sunday_hours = (end - start).total_seconds() / 3600
                                helgetimer += sunday_hours

                                # Counts evening hours
                                if start.time() >= time(14, 0):
                                    helgetimer_ettermiddag += sunday_hours

                                # Counts daytime hours in weekend
                                if start.time() < time(14, 0):
                                    helgetimer_dagtid += sunday_hours

                            helgedager += 1


                        ### TIDLIGVAKTER — aligned with shift-classifier.js
                        # Starts before 12:00 and is not a night shift
                        if start.time() < time(12, 0) and not is_night:
                            tidlig += 1
                            ### STARTS BEFORE 6 ####
                            if start.time() < time(6, 0):
                                before_6 += 1
                            elif start.time() < time(8, 0):
                                tidlig_6_8 += 1
                            else:
                                tidlig_8_12 += 1

                        ### KVELDSVAKT — aligned with shift-classifier.js
                        # Starts 12:00+ and either ends same day, or crosses
                        # midnight but ends before 04:00 (not a true nattevakt)
                        is_kveldsvakt = (
                            start.time() >= time(12, 0)
                            and not is_night
                        )
                        if is_kveldsvakt:
                            afternoon_count += 1
                            if not crosses_midnight and end.time() <= time(20):
                                afternoon_ends_before_20 += 1
                            current_kveld_streak += 1
                            afternons_in_row = max(afternons_in_row, current_kveld_streak)
                        else:
                            current_kveld_streak = 0
                                    

                #### TEST ####
                #print(f"{_dagsverk['turnus']}, {_dagsverk['uke_nr']}, {_dagsverk['ukedag']}, {sunday_hours}")

            avg_shift_hours = round(total_shift_hours / shift_cnt, 1) if shift_cnt > 0 else 0

            # Day-of-week off rates (fraction of each weekday that is a day off)
            mon_off_rate = round(weekday_off['mon'] / weekday_total['mon'], 3) if weekday_total['mon'] else 0
            tue_off_rate = round(weekday_off['tue'] / weekday_total['tue'], 3) if weekday_total['tue'] else 0
            wed_off_rate = round(weekday_off['wed'] / weekday_total['wed'], 3) if weekday_total['wed'] else 0
            thu_off_rate = round(weekday_off['thu'] / weekday_total['thu'], 3) if weekday_total['thu'] else 0
            fri_off_rate = round(weekday_off['fri'] / weekday_total['fri'], 3) if weekday_total['fri'] else 0
            sat_off_rate = round(weekday_off['sat'] / weekday_total['sat'], 3) if weekday_total['sat'] else 0
            sun_off_rate = round(weekday_off['sun'] / weekday_total['sun'], 3) if weekday_total['sun'] else 0

            # Start time standard deviation (minutes from midnight) — measures schedule consistency
            start_time_std = round(float(np.std(start_times_minutes)), 1) if start_times_minutes else 0

            # Adds shift as new row to dataframe
            new_row = pd.DataFrame({
                'turnus': [turnus_navn],
                'shift_cnt': [shift_cnt],
                'tidlig': [tidlig],
                'ettermiddag' : [afternoon_count],
                'natt': [night_count],
                'natt_helg': [round(natt_helg,1)],
                'helgetimer': [round(helgetimer,1)],
                'helgedager': [helgedager],
                'helgetimer_dagtid': [round(helgetimer_dagtid,1)],
                'helgetimer_ettermiddag': [round(helgetimer_ettermiddag)],
                'before_6': [before_6],
                'afternoon_ends_before_20': [afternoon_ends_before_20],
                'afternoons_in_row': [afternons_in_row],
                'tidlig_6_8': [tidlig_6_8],
                'tidlig_8_12': [tidlig_8_12],
                'longest_off_streak': [longest_off_streak],
                'longest_work_streak': [longest_work_streak],
                'avg_shift_hours': [avg_shift_hours],
                'mon_off_rate': [mon_off_rate],
                'tue_off_rate': [tue_off_rate],
                'wed_off_rate': [wed_off_rate],
                'thu_off_rate': [thu_off_rate],
                'fri_off_rate': [fri_off_rate],
                'sat_off_rate': [sat_off_rate],
                'sun_off_rate': [sun_off_rate],
                'start_time_std': [start_time_std],
                })
            
            self.stats_df = pd.concat([self.stats_df, new_row], ignore_index=True)


def generate_statistics_for_year(year_id):
    """Generate statistics for a specific year"""
    import os
    turnus_path = os.path.join(AppConfig.static_dir, 'turnusfiler', year_id.lower(), f'turnus_schedule_{year_id}.json')
    df_path = os.path.join(AppConfig.static_dir, 'turnusfiler', year_id.lower(), f'turnus_stats_{year_id}.json')
    
    if not os.path.exists(turnus_path):
        print(f"❌ Error: File {turnus_path} does not exist")
        return
    
    print(f"Generating statistics for {year_id}...")
    turnus = Turnus(turnus_path)
    turnus.stats_df.to_json(df_path)
    
    print(f"✅ Statistics generated: {df_path}")
    print(f"Total turnuses: {len(turnus.stats_df)}")
    print("\nSample statistics:")
    print(turnus.stats_df[['turnus', 'shift_cnt', 'tidlig', 'tidlig_6_8', 'tidlig_8_12', 'ettermiddag', 'natt', 'helgetimer', 'longest_off_streak', 'longest_work_streak', 'avg_shift_hours']].head(10))
    return turnus.stats_df

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate shift statistics for turnus files')
    parser.add_argument('year', nargs='?', default='R26', help='Year identifier (e.g., R24, R25, R26). Default: R26')
    parser.add_argument('--all', action='store_true', help='Generate statistics for all available years')
    
    args = parser.parse_args()
    
    if args.all:
        # Generate for all available years
        import os
        turnusfiler_dir = os.path.join(AppConfig.static_dir, 'turnusfiler')
        years = [d for d in os.listdir(turnusfiler_dir) if os.path.isdir(os.path.join(turnusfiler_dir, d))]
        years.sort()
        
        for year in years:
            year_upper = year.upper()
            print(f"\n{'='*50}")
            generate_statistics_for_year(year_upper)
    else:
        generate_statistics_for_year(args.year)