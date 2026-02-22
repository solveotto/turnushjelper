import pandas as pd
import json
import openpyxl
import os
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from config import AppConfig
from app.utils import db_utils, df_utils


class TurnusnokkelGen():
    def __init__(self, turnus_name=None, turnus_set_id=None):
        self.turnus_set_id = turnus_set_id
        self.turnus_name = turnus_name
        self.sheet_name = 'Turnusnøkkel'
        self.start_row = 51
        self.start_col = 1
        
        # Set file path based on turnus set if available
        if self.turnus_set_id:
            turnus_set = db_utils.get_turnus_set_by_id(self.turnus_set_id)
            if turnus_set:
                year_identifier = turnus_set['year_identifier']
                self.file_path = f'{AppConfig.turnusfiler_dir}/{year_identifier.lower()}/turnusnøkkel_{year_identifier}_org.xlsx'
            else:
                # Fallback to R25 if turnus set not found
                self.file_path = f'{AppConfig.turnusfiler_dir}/turnusnøkkel_R25_org.xlsx'
        else:
            # Fallback to R25 if no turnus set ID provided
            self.file_path = f'{AppConfig.turnusfiler_dir}/turnusnøkkel_R25_org.xlsx'
        
        # Only load workbook if we're not doing single turnus generation
        # (single generation uses its own path logic)
        if not self.turnus_name:
            self.workbook, self.sheet = self.get_turnusnøkkel_excel_data()
   
    # Step 1: Load the existing Excel file
    def get_turnusnøkkel_excel_data(self):
        # This method is mainly used for the legacy generate_all_turnus_nokkel
        # For single turnus generation, we use the proper path in generate_single_turnus_nokkel
        excel_file = 'turnusnøkkel_R25_org.xlsx'
        if os.path.exists(excel_file):
            workbook = load_workbook(excel_file)
            sheet = workbook.active
            return workbook, sheet
        else:
            # Fallback: try to find it in the proper location
            try:
                from config import AppConfig
                fallback_path = f'{AppConfig.turnusfiler_dir}/turnusnøkkel_R25_org.xlsx'
                if os.path.exists(fallback_path):
                    workbook = load_workbook(fallback_path)
                    sheet = workbook.active
                    return workbook, sheet
            except (ImportError, AttributeError, FileNotFoundError):
                pass
            raise FileNotFoundError(f"Excel template file not found: {excel_file}")


    def generate_single_turnus_nokkel(self):
        """
        Generate turnusnøkkel Excel file for a specific turnus
        
        Returns:
            dict: {'success': bool, 'filename': str, 'error': str}
        """
        try:
            if not self.turnus_name or not self.turnus_set_id:
                return {'success': False, 'error': 'Missing turnus name or turnus set ID'}
            
            # Get the turnus data for the specific turnus set
            df_manager = df_utils.DataframeManager(self.turnus_set_id)
            turnus_data = df_manager.turnus_data
            
            # Find the specific turnus data
            target_turnus_data = None
            for turnus_dict in turnus_data:
                if self.turnus_name in turnus_dict:
                    target_turnus_data = turnus_dict[self.turnus_name]
                    break
            
            if not target_turnus_data:
                return {'success': False, 'error': f'Turnus "{self.turnus_name}" not found in turnus set {self.turnus_set_id}'}
            
            # Get turnus set info for file paths
            turnus_set = db_utils.get_turnus_set_by_id(self.turnus_set_id)
            if not turnus_set:
                return {'success': False, 'error': f'Turnus set {self.turnus_set_id} not found'}
            
            year_identifier = turnus_set['year_identifier']
            
            # Define file paths based on turnus set
            # Get the project root directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            base_path = os.path.join(project_root, 'app', 'static', 'turnusfiler', year_identifier.lower())
            excel_template = os.path.join(base_path, f'turnusnøkkel_{year_identifier}_org.xlsx')
            
            # Debug info for error reporting
            debug_info = f"year_identifier={year_identifier}, base_path={base_path}, template={excel_template}"
            
            # Check if template exists
            if not os.path.exists(excel_template):
                # List available files in the directory for debugging
                available_files = []
                if os.path.exists(base_path):
                    available_files = os.listdir(base_path)
                
                error_msg = f'Template file not found: {excel_template}\n'
                error_msg += f'Debug info: {debug_info}\n'
                error_msg += f'Base path exists: {os.path.exists(base_path)}\n'
                error_msg += f'Available files in base path: {available_files}'
                return {'success': False, 'error': error_msg}
            
            # Load the existing Excel file
            workbook = load_workbook(excel_template)
            sheet = workbook.active
            
            # Access the specific sheet
            if self.sheet_name in workbook.sheetnames:
                sheet = workbook[self.sheet_name]
            else:
                return {'success': False, 'error': f"Sheet '{self.sheet_name}' not found in the Excel file"}
            
            for name in workbook.sheetnames:
                if name != self.sheet_name:
                    workbook[name].sheet_state = 'hidden'
            
            # Process the turnus data and insert into Excel
            # Skip non-dict entries (e.g. 'kl_timer', 'tj_timer' metadata strings)
            for uke_nr, ukedata in target_turnus_data.items():
                if not isinstance(ukedata, dict):
                    continue
                for dag_nr, dag_data in ukedata.items():
                    try:
                        start_value = dag_data['tid'][0] if dag_data['tid'] and len(dag_data['tid']) > 0 else ''
                    except (IndexError, KeyError, TypeError):
                        start_value = ''

                    try:
                        end_value = dag_data['tid'][1] if dag_data['tid'] and len(dag_data['tid']) > 1 else ''
                    except (IndexError, KeyError, TypeError):
                        end_value = ''
                    
                    # Create cell value
                    if start_value and end_value:
                        cell_value = f'{start_value} - {end_value}'
                    elif start_value:
                        cell_value = start_value
                    else:
                        cell_value = ''

                    # Set the value in the appropriate cell
                    col_letter = get_column_letter(self.start_col + int(dag_nr))
                    sheet[f"{col_letter}{self.start_row + int(uke_nr)}"] = cell_value

            # Reset scroll position so the sheet opens at the top
            sheet.sheet_view.topLeftCell = 'A1'

            # Generate filename (no need to save to disk)
            filename = f"Turnusnøkkel_{self.turnus_name}_{year_identifier}.xlsx"
            
            # Return the workbook object instead of saving to disk
            return {'success': True, 'filename': filename, 'workbook': workbook}
            
        except Exception as e:
            return {'success': False, 'error': f'Error generating turnusnøkkel: {str(e)}'}


    def generate_all_turnus_nokkel(self):

        # Step 2: Access a specific sheet by name
        if self.sheet_name in self.workbook.sheetnames:
            sheet = self.workbook[self.sheet_name]
        else:
            raise ValueError(f"Sheet '{self.sheet_name}' not found in the Excel file.")

        # Step 2: Load the JSON file (assuming a 7x6 table structure)
        with open('turnuser_R25.json', 'r') as file:
            json_data = json.load(file)

        # Step 4: Specify where to start inserting the data
        start_row = 51  # Row 2, for example
        start_col = 1  # Column B (2nd column)


        # Step 4: Extract 'start' and 'end' from each nested dictionary and insert them into cells
        for turnus in json_data:
            for turnus_navn, turnus_data in turnus.items():
                # Step 1: Load the existing Excel file
                excel_file = 'turnusnøkkel_R25_org.xlsx'
                workbook = load_workbook(excel_file)
                sheet = workbook.active  # Select the active sheet, or specify the sheet name

                # Step 2: Access a specific sheet by name
                sheet_name = 'Turnusnøkkel'
                if sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                else:
                    raise ValueError(f"Sheet '{sheet_name}' not found in the Excel file.")

                for uke_nr, ukedata in turnus_data.items():
                    if not isinstance(ukedata, dict):
                        continue
                    for dag_nr, dag_data in ukedata.items():
                    
                        try:
                            start_value = dag_data['tid'][0]
                        except IndexError:
                            start_value = ''

                        try:
                            end_value = dag_data['tid'][1]
                        except IndexError:
                            end_value = ''
                        
                        
                        cell_value = f'{start_value} - {end_value}' if start_value and end_value else f"{start_value}"

                        # Set the 'start' value in the first column of this row
                        col_letter_start = get_column_letter(start_col+int(dag_nr))
                        sheet[f"{col_letter_start}{start_row + int(uke_nr)}"] = cell_value
                    
                # Save the updated Excel file with a new name
                filename = f"Turnusnøkkel_{turnus_navn}.xlsx"
                workbook.save(filename)
                    

if __name__ == "__main__":
    # Example usage
    generator = TurnusnokkelGen()
    generator.generate_all_turnus_nokkel()