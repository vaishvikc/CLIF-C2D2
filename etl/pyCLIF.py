import pandas as pd
import numpy as np
import json
import os
import duckdb
import matplotlib.pyplot as plt
import pytz
from datetime import datetime
from typing import Union
from functools import reduce

conn = duckdb.connect(database=':memory:')

def load_config():
    project_root = os.path.dirname(os.path.dirname(__file__))
    json_path = os.path.join(project_root, 'config', 'config.json')
    
    with open(json_path, 'r') as file:
        config = json.load(file)
    print("✅ Loaded configuration from config.json")
    return config

helper = load_config()

def _cast_id_cols_to_string(df):
    id_cols = [c for c in df.columns if c.endswith("_id")]
    if id_cols:                                   # no-op if none found
        df[id_cols] = df[id_cols].astype("string")
    return df

def load_parquet_with_tz(file_path, columns=None, filters=None, sample_size=None):
    con = duckdb.connect()
    # DuckDB >=0.9 understands the original zone if we ask for TIMESTAMPTZ
    con.execute("SET timezone = 'UTC';")          # read & return in UTC
    con.execute("SET pandas_analyze_sample=0;")   # avoid sampling issues

    sel = "*" if columns is None else ", ".join(columns)
    query = f"SELECT {sel} FROM parquet_scan('{file_path}')"

    if filters:                                  # optional WHERE clause
        clauses = []
        for col, val in filters.items():
            if isinstance(val, list):
                vals = ", ".join([f"'{v}'" for v in val])
                clauses.append(f"{col} IN ({vals})")
            else:
                clauses.append(f"{col} = '{val}'")
        query += " WHERE " + " AND ".join(clauses)
    if sample_size:
        query += f" LIMIT {sample_size}"

    df = con.execute(query).fetchdf()            # pandas DataFrame
    con.close()
    df = _cast_id_cols_to_string(df)         # cast id columns to string
    return df

def load_data(table, sample_size=None, columns=None, filters=None):
    """
    Load data from a file in the specified directory with the option to select specific columns and apply filters.

    Parameters:
        table (str): The name of the table to load.
        sample_size (int, optional): Number of rows to load.
        columns (list of str, optional): List of column names to load.
        filters (dict, optional): Dictionary of filters to apply.

    Returns:
        pd.DataFrame: DataFrame containing the requested data.
    """
    # Determine the file path based on the directory and filetype
    file_name = f"{table}.{helper['file_type']}"
    file_path = os.path.join(helper['tables_path'], file_name)
    
    # Load the data based on filetype
    if os.path.exists(file_path):
        if helper['file_type'] == 'csv':
            # For CSV, we can use DuckDB to read specific columns and apply filters efficiently
            con = duckdb.connect()
            # Build the SELECT clause
            select_clause = "*" if not columns else ", ".join(columns)
            # Start building the query
            query = f"SELECT {select_clause} FROM read_csv_auto('{file_path}')"
            # Apply filters
            if filters:
                filter_clauses = []
                for column, values in filters.items():
                    if isinstance(values, list):
                        # Escape single quotes and wrap values in quotes
                        values_list = ', '.join(["'" + str(value).replace("'", "''") + "'" for value in values])
                        filter_clauses.append(f"{column} IN ({values_list})")
                    else:
                        value = str(values).replace("'", "''")
                        filter_clauses.append(f"{column} = '{value}'")
                if filter_clauses:
                    query += " WHERE " + " AND ".join(filter_clauses)
            # Apply sample size limit
            if sample_size:
                query += f" LIMIT {sample_size}"
            # Execute the query and fetch the data
            df = con.execute(query).fetchdf()
            con.close()
        elif helper['file_type'] == 'parquet':
            df = load_parquet_with_tz(file_path, columns, filters, sample_size)
        else:
            raise ValueError("Unsupported filetype. Only 'csv' and 'parquet' are supported.")
        print(f"Data loaded successfully from {file_path}")
        df = _cast_id_cols_to_string(df) # Cast id columns to string
        return df
    else:
        raise FileNotFoundError(f"The file {file_path} does not exist in the specified directory.")

def convert_datetime_columns_to_site_tz(df, site_tz_str, verbose=True):
    """
    Convert all datetime columns in the DataFrame to the specified site timezone.

    Parameters:
    - df (pd.DataFrame): Input DataFrame.
    - site_tz_str (str): Timezone string, e.g., "America/New_York". or "US/Central"
    - verbose (bool): Whether to print detailed output (default: True).

    Returns:
    - pd.DataFrame: Modified DataFrame with datetime columns converted.
    """
    site_tz = pytz.timezone(site_tz_str)

    # Identify datetime-related columns
    dttm_columns = [col for col in df.columns if 'dttm' in col]

    for col in dttm_columns:
        df[col] = pd.to_datetime(df[col], errors='coerce')
        if pd.api.types.is_datetime64tz_dtype(df[col]):
            current_tz = df[col].dt.tz
            if current_tz == site_tz:
                if verbose:
                    print(f"{col}: Already in your timezone ({current_tz}), no conversion needed.")
            elif current_tz == pytz.UTC:
                print(f"{col}: null count before conversion= {df[col].isna().sum()}")
                df[col] = df[col].dt.tz_convert(site_tz)
                if verbose:
                    print(f"{col}: Converted from UTC to your timezone ({site_tz}).")
                    print(f"{col}: null count after conversion= {df[col].isna().sum()}")
            else:
                print(f"{col}: null count before conversion= {df[col].isna().sum()}")
                df[col] = df[col].dt.tz_convert(site_tz)
                if verbose:
                    print(f"{col}: Your timezone is {current_tz}, Converting to your site timezone ({site_tz}).")
                    print(f"{col}: null count after conversion= {df[col].isna().sum()}")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            if verbose:
                df[col] = df[col].dt.tz_localize(site_tz, ambiguous=True, nonexistent='shift_forward')
                print(f"WARNING: {col}: Naive datetime, NOT converting. Assuming it's in your LOCAL ZONE. Please check ETL!")
        else:
            if verbose:
                print(f"WARNING: {col}: Not a datetime column. Please check ETL and run again!")
    return df



def count_unique_encounters(df, encounter_column='hospitalization_id'):
    """
    Counts the unique encounters in a DataFrame.
    
    Parameters:
    df (DataFrame): The DataFrame to analyze.
    encounter_column (str): The name of the column containing encounter IDs (default is 'hospitalization_id').
    
    Returns:
    int: The number of unique encounters.
    """
    return df[encounter_column].nunique()

def generate_facetgrid_histograms(data, category_column, value_column):
    """
    Generate histograms using seaborn's FacetGrid.

    Parameters:
        data (DataFrame): DataFrame containing the data.
        category_column (str): Name of the column containing categories.
        value_column (str): Name of the column containing values.

    Returns:
        FacetGrid: Seaborn FacetGrid object containing the generated histograms.
    """
    # Create a FacetGrid
    g = sns.FacetGrid(data, col=category_column, col_wrap=6, sharex=False, sharey=False)
    g.map(sns.histplot, value_column, bins=30, color='blue', edgecolor='black')

    # Set titles and labels
    g.set_titles('{col_name}')
    g.set_axis_labels(value_column, 'Frequency')

    # Adjust layout
    plt.subplots_adjust(top=0.9)
    g.fig.suptitle(f'Histograms of {value_column} by {category_column}', fontsize=16)

    return g

def map_race_column(df, race_column='race'):
    """
    Function to map race values to simplified categories.

    Args:
    - df (pandas.DataFrame): Input DataFrame containing the race data.
    - race_column (str): The name of the race column. Default is 'race'.

    Returns:
    - pandas.DataFrame: DataFrame with a new column 'race_new' containing the mapped race values.
    """
    # Define the mapping
    race_mapping = {
        'Black or African-American': 'Black',
        'Black or African American': 'Black',
        'White': 'White',
        'Asian': 'Other',
        'American Indian or Alaska Native': 'Other',
        'Native Hawaiian or Other Pacific Islander': 'Other',
        'Other': 'Other',
        'Unknown': 'Other'
    }

    # Apply the mapping to create a new 'race_new' column
    df['race_new'] = df[race_column].map(race_mapping).fillna('Missing')

    return df


def remove_duplicates(df, columns, df_name):
    """
    Checks for and removes duplicate rows in a DataFrame based on the combination of specified columns.

    Parameters:
        df (DataFrame): The DataFrame to clean.
        columns (list): A list of columns to use for identifying duplicates.
        df_name (str): The name of the DataFrame (for display purposes).

    Returns:
        DataFrame: The DataFrame with duplicates removed.
    """
    # Check for duplicates based on the combination of specified columns
    initial_count = len(df)
    duplicates = df[df.duplicated(subset=columns, keep=False)]
    
    print(f"Processing DataFrame: {df_name}")
    
    if not duplicates.empty:
        num_duplicates = len(duplicates)
        print(f"Found {num_duplicates} duplicate rows based on columns: {columns}")
        
        # Drop duplicates, keeping the first occurrence
        df_cleaned = df.drop_duplicates(subset=columns, keep='first')
        final_count = len(df_cleaned)
        duplicates_dropped = initial_count - final_count
        
        print(f"Dropped {duplicates_dropped} duplicate rows. New DataFrame has {final_count} rows.")
    else:
        df_cleaned = df
        print(f"No duplicates found based on columns: {columns}.")
    
    return df_cleaned

def apply_outlier_thresholds(df, col_name, min_val, max_val):
    """
    Helper function to clamp column values between min and max thresholds, 
    setting values outside range to NaN.
    
    Parameters:
        df (pd.DataFrame): DataFrame containing the column to process
        col_name (str): Name of the column to apply thresholds to
        min_val (float): Minimum allowed value (inclusive)
        max_val (float): Maximum allowed value (inclusive)
        
    Returns:
        None: Modifies the DataFrame in place by updating the specified column
    """
    df[col_name] = df[col_name].where(df[col_name].between(min_val, 
                                                           max_val, 
                                                           inclusive='both'), 
                                                           np.nan)

# def process_resp_support(df):
#     """
#     Process the respiratory support data using waterfall logic.
    
#     Parameters:
#         df (pd.DataFrame): DataFrame containing respiratory support data.
        
#     Returns:
#         pd.DataFrame: Processed DataFrame with filled values.
#     """
#     print("Initiating waterfall processing...")
    
#     # Ensure 'recorded_dttm' is in datetime format
#     df['recorded_dttm'] = pd.to_datetime(df['recorded_dttm'])
    
#     # Convert categories to lowercase to standardize
#     df['device_category'] = df['device_category'].str.lower()
#     df['mode_category'] = df['mode_category'].str.lower()
#     df['device_name'] = df['device_name'].str.lower()
#     df['mode_name'] = df['mode_name'].str.lower()
    
#     # # Fix out-of-range values
#     # print("Fixing out-of-range values for 'fio2_set', 'peep_set', and 'resp_rate_set'...")
#     # df['fio2_set'] = df['fio2_set'].where(df['fio2_set'].between(0.21, 1), np.nan)
#     # df['peep_set'] = df['peep_set'].where(df['peep_set'].between(0, 50), np.nan)
#     # df['resp_rate_set'] = df['resp_rate_set'].where(df['resp_rate_set'].between(0, 60), np.nan)
    
#     # Create 'recorded_date' and 'recorded_hour'
#     print('Creating recorded_date and recorded_hour...')
#     df['recorded_date'] = df['recorded_dttm'].dt.date
#     df['recorded_hour'] = df['recorded_dttm'].dt.hour
    
#     # Sort data
#     print("Sorting data by 'hospitalization_id' and 'recorded_dttm'...")
#     df.sort_values(by=['hospitalization_id', 'recorded_dttm'], inplace=True)
    
#     # Fix missing 'device_category' and 'device_name' based on 'mode_category'
#     print("Fixing missing 'device_category' and 'device_name' based on 'mode_category'...")
#     mask = (
#         df['device_category'].isna() &
#         df['device_name'].isna() &
#         df['mode_category'].str.contains('assist control-volume control|simv|pressure control', case=False, na=False)
#     )
#     df.loc[mask, 'device_category'] = 'imv'
#     df.loc[mask, 'device_name'] = 'mechanical ventilator'
    
#     # Fix 'device_category' and 'device_name' based on neighboring records
#     print("Fixing 'device_category' and 'device_name' based on neighboring records...")
#     # Create shifted columns once to avoid multiple shifts
#     df['device_category_shifted'] = df['device_category'].shift()
#     df['device_category_shifted_neg'] = df['device_category'].shift(-1)
    
#     condition_prev = (
#         df['device_category'].isna() &
#         (df['device_category_shifted'] == 'imv') &
#         df['resp_rate_set'].gt(1) &
#         df['peep_set'].gt(1)
#     )
#     condition_next = (
#         df['device_category'].isna() &
#         (df['device_category_shifted_neg'] == 'imv') &
#         df['resp_rate_set'].gt(1) &
#         df['peep_set'].gt(1)
#     )
    
#     condition = condition_prev | condition_next
#     df.loc[condition, 'device_category'] = 'imv'
#     df.loc[condition, 'device_name'] = 'mechanical ventilator'
    
#     # Drop the temporary shifted columns
#     df.drop(['device_category_shifted', 'device_category_shifted_neg'], axis=1, inplace=True)
    
#     # Handle duplicates and missing data
#     print("Handling duplicates and removing rows with all key variables missing...")
#     df['n'] = df.groupby(['hospitalization_id', 'recorded_dttm'])['recorded_dttm'].transform('size')
#     df = df[~((df['n'] > 1) & (df['device_category'] == 'nippv'))]
#     df = df[~((df['n'] > 1) & (df['device_category'].isna()))]
#     subset_vars = ['device_category', 'device_name', 'mode_category', 'mode_name', 'fio2_set']
#     df.dropna(subset=subset_vars, how='all', inplace=True)
#     df.drop_duplicates(subset=['hospitalization_id', 'recorded_dttm'], keep='first', inplace=True)
#     df.drop('n', axis=1, inplace=True)  # Drop 'n' as it's no longer needed
    
#     # Fill forward 'device_category' within each hospitalization
#     print("Filling forward 'device_category' within each hospitalization...")
#     df['device_category'] = df.groupby('hospitalization_id')['device_category'].ffill()
    
#     # Create 'device_cat_id' based on changes in 'device_category'
#     print("Creating 'device_cat_id' to track changes in 'device_category'...")
#     df['device_cat_f'] = df['device_category'].fillna('missing').astype('category').cat.codes
#     df['device_cat_change'] = df['device_cat_f'] != df.groupby('hospitalization_id')['device_cat_f'].shift()
#     df['device_cat_change'] = df['device_cat_change'].astype(int)
#     df['device_cat_id'] = df.groupby('hospitalization_id')['device_cat_change'].cumsum()
#     df.drop('device_cat_change', axis=1, inplace=True)
    
#     # Fill 'device_name' within 'device_cat_id'
#     print("Filling 'device_name' within each 'device_cat_id'...")
#     df['device_name'] = df.groupby(['hospitalization_id', 'device_cat_id'])['device_name'].ffill().bfill()
    
#     # Create 'device_id' based on changes in 'device_name'
#     print("Creating 'device_id' to track changes in 'device_name'...")
#     df['device_name_f'] = df['device_name'].fillna('missing').astype('category').cat.codes
#     df['device_name_change'] = df['device_name_f'] != df.groupby('hospitalization_id')['device_name_f'].shift()
#     df['device_name_change'] = df['device_name_change'].astype(int)
#     df['device_id'] = df.groupby('hospitalization_id')['device_name_change'].cumsum()
#     df.drop('device_name_change', axis=1, inplace=True)
    
#     # Fill 'mode_category' within 'device_id'
#     print("Filling 'mode_category' within each 'device_id'...")
#     df['mode_category'] = df.groupby(['hospitalization_id', 'device_id'])['mode_category'].ffill().bfill()
    
#     # Create 'mode_cat_id' based on changes in 'mode_category'
#     print("Creating 'mode_cat_id' to track changes in 'mode_category'...")
#     df['mode_cat_f'] = df['mode_category'].fillna('missing').astype('category').cat.codes
#     df['mode_cat_change'] = df['mode_cat_f'] != df.groupby(['hospitalization_id', 'device_id'])['mode_cat_f'].shift()
#     df['mode_cat_change'] = df['mode_cat_change'].astype(int)
#     df['mode_cat_id'] = df.groupby(['hospitalization_id', 'device_id'])['mode_cat_change'].cumsum()
#     df.drop('mode_cat_change', axis=1, inplace=True)
    
#     # Fill 'mode_name' within 'mode_cat_id'
#     print("Filling 'mode_name' within each 'mode_cat_id'...")
#     df['mode_name'] = df.groupby(['hospitalization_id', 'mode_cat_id'])['mode_name'].ffill().bfill()
    
#     # Create 'mode_name_id' based on changes in 'mode_name'
#     print("Creating 'mode_name_id' to track changes in 'mode_name'...")
#     df['mode_name_f'] = df['mode_name'].fillna('missing').astype('category').cat.codes
#     df['mode_name_change'] = df['mode_name_f'] != df.groupby(['hospitalization_id', 'mode_cat_id'])['mode_name_f'].shift()
#     df['mode_name_change'] = df['mode_name_change'].astype(int)
#     df['mode_name_id'] = df.groupby(['hospitalization_id', 'mode_cat_id'])['mode_name_change'].cumsum()
#     df.drop('mode_name_change', axis=1, inplace=True)
    
#     # Adjust 'fio2_set' for 'room air' device_category
#     print("Adjusting 'fio2_set' for 'room air' device_category...")
#     df['fio2_set'] = np.where(df['fio2_set'].isna() & (df['device_category'] == 'room air'), 0.21, df['fio2_set'])
    
#     # Adjust 'mode_category' for 't-piece' devices
#     print("Adjusting 'mode_category' for 't-piece' devices...")
#     mask_tpiece = (
#         df['mode_category'].isna() &
#         df['device_name'].str.contains('t-piece', case=False, na=False)
#     )
#     df.loc[mask_tpiece, 'mode_category'] = 'blow by'
    
#     # Fill remaining variables within 'mode_name_id'
#     print("Filling remaining variables within each 'mode_name_id'...")
#     fill_vars = [
#         'fio2_set', 'lpm_set', 'peep_set', 'resp_rate_set',
#         'resp_rate_obs'
#     ]
#     df[fill_vars] = df.groupby(['hospitalization_id', 'mode_name_id'])[fill_vars].transform(lambda x: x.ffill().bfill())
    
#     # Fill 'tracheostomy' forward within each hospitalization
#     print("Filling 'tracheostomy' forward within each hospitalization...")
#     df['tracheostomy'] = df.groupby('hospitalization_id')['tracheostomy'].ffill()
    
#     # Remove duplicates
#     print("Removing duplicates...")
#     df.drop_duplicates(inplace=True)
    
#     # Select relevant columns
#     columns_to_keep = [
#         'hospitalization_id', 'recorded_dttm', 'recorded_date', 'recorded_hour',
#         'device_category', 'device_name', 'mode_category', 'mode_name',
#         'device_cat_id', 'device_id', 'mode_cat_id', 'mode_name_id',
#         'fio2_set', 'lpm_set', 'peep_set', 'resp_rate_set',
#         'tracheostomy', 'resp_rate_obs'
#     ]
#     # Ensure columns exist before selecting
#     existing_columns = [col for col in columns_to_keep if col in df.columns]
#     df = df[existing_columns]
    
#     print("Waterfall processing completed.")
#     return df

def stitch_encounters(hospitalization, adt, time_interval=6):
    """
    Stitches together related hospital encounters that occur within a specified time interval of each other.
    
    Args:
        hospitalization (pd.DataFrame): Hospitalization table with required columns
        adt (pd.DataFrame): ADT table with required columns
        time_interval (int, optional): Number of hours between encounters to consider them linked. Defaults to 6.
        
    Returns:
        pd.DataFrame: Stitched encounters with encounter blocks
    """
    hospitalization_filtered = hospitalization[["patient_id","hospitalization_id","admission_dttm",
                                                "discharge_dttm","age_at_admission",  "discharge_category"]].copy()
    hospitalization_filtered['admission_dttm'] = pd.to_datetime(hospitalization_filtered['admission_dttm'])
    hospitalization_filtered['discharge_dttm'] = pd.to_datetime(hospitalization_filtered['discharge_dttm'])

    hosp_adt_join = pd.merge(hospitalization_filtered[["patient_id","hospitalization_id","age_at_admission",
                                                       "admission_dttm","discharge_dttm",
                                                        "discharge_category"]], 
                      adt[["hospitalization_id","in_dttm","out_dttm","location_category","hospital_id"]],
                 on="hospitalization_id",how="left")

    hospital_cat = hosp_adt_join[["hospitalization_id","in_dttm","out_dttm","hospital_id"]]

    # Step 1: Sort by patient_id and admission_dttm
    hospital_block = hosp_adt_join[["patient_id","hospitalization_id","admission_dttm","discharge_dttm", "age_at_admission",  "discharge_category"]]
    hospital_block = hospital_block.drop_duplicates()
    hospital_block = hospital_block.sort_values(by=["patient_id", "admission_dttm"]).reset_index(drop=True)
    hospital_block = hospital_block[["patient_id","hospitalization_id","admission_dttm","discharge_dttm", "age_at_admission",  "discharge_category"]]

    # Step 2: Calculate time between discharge and next admission
    hospital_block["next_admission_dttm"] = hospital_block.groupby("patient_id")["admission_dttm"].shift(-1)
    hospital_block["discharge_to_next_admission_hrs"] = (
        (hospital_block["next_admission_dttm"] - hospital_block["discharge_dttm"]).dt.total_seconds() / 3600
    )

    # Step 3: Create linked column based on time_interval
    hospital_block["linked6hrs"] = hospital_block["discharge_to_next_admission_hrs"] < time_interval

    # Sort values to ensure correct order
    hospital_block = hospital_block.sort_values(by=["patient_id", "admission_dttm"]).reset_index(drop=True)

    # Initialize encounter_block with row indices + 1
    hospital_block['encounter_block'] = hospital_block.index + 1

    # Iteratively propagate the encounter_block values
    while True:
        shifted = hospital_block['encounter_block'].shift(-1)
        mask = hospital_block['linked6hrs'] & (hospital_block['patient_id'] == hospital_block['patient_id'].shift(-1))
        hospital_block.loc[mask, 'encounter_block'] = shifted[mask]
        if hospital_block['encounter_block'].equals(hospital_block['encounter_block'].bfill()):
            break

    hospital_block['encounter_block'] = hospital_block['encounter_block'].bfill(downcast='int')
    hospital_block = pd.merge(hospital_block,hospital_cat,how="left",on="hospitalization_id")
    hospital_block = hospital_block.sort_values(by=["patient_id", "admission_dttm","in_dttm","out_dttm"]).reset_index(drop=True)
    hospital_block = hospital_block.drop_duplicates()

    hospital_block2 = hospital_block.groupby(['patient_id','encounter_block']).agg(
        admission_dttm=pd.NamedAgg(column='admission_dttm', aggfunc='min'),
        discharge_dttm=pd.NamedAgg(column='discharge_dttm', aggfunc='max'),
        # admission_type_category=pd.NamedAgg(column='admission_type_category', aggfunc='first'),
        discharge_category=pd.NamedAgg(column='discharge_category', aggfunc='last'),
        hospital_id = pd.NamedAgg(column='hospital_id', aggfunc='last'),
        age_at_admission=pd.NamedAgg(column='age_at_admission', aggfunc='last'),
        list_hospitalization_id=pd.NamedAgg(column='hospitalization_id', aggfunc=lambda x: sorted(x.unique()))
    ).reset_index()

    df = pd.merge(hospital_block[["patient_id",
                                  "hospitalization_id",
                                  "encounter_block"]].drop_duplicates(),
             hosp_adt_join[["hospitalization_id","location_category","in_dttm","out_dttm"]], on="hospitalization_id",how="left")

    df = pd.merge(df,hospital_block2[["encounter_block",
                                      "admission_dttm",
                                      "discharge_dttm",
                                      "discharge_category",
                                      "hospital_id",
                                     "list_hospitalization_id"]],on="encounter_block",how="left")
    df = df.drop_duplicates(subset=["patient_id","encounter_block","in_dttm","out_dttm","location_category"])
    
    return df

def create_summary_table(
    df, 
    numeric_col, 
    group_by_cols=None
):
    """
    Create a summary table for a given numeric column in a DataFrame, optionally grouped.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing your data.
    numeric_col : str
        The name of the numeric column to summarize (e.g., 'fio2_set').
    group_by_cols : str or list of str, optional
        Column name(s) to group by (e.g., 'device_category', ['device_category','mode_category'], etc.).
        If None, the function provides a single overall summary for the entire df.

    Returns
    -------
    pd.DataFrame
        A DataFrame with columns for each statistic: 
        ['N', 'missing', 'min', 'q25', 'median', 'q75', 'mean', 'max'].
        If group_by_cols is provided, those columns appear first in the output.
    """

    # 1) Define helper functions for quartiles & missing
    def q25(x):
        return x.quantile(0.25)
    q25.__name__ = 'q25'

    def q50(x):
        return x.quantile(0.50)
    q50.__name__ = 'median'

    def q75(x):
        return x.quantile(0.75)
    q75.__name__ = 'q75'

    def missing_count(x):
        return x.isna().sum()
    missing_count.__name__ = 'missing'

    # 2) Build an aggregation dictionary for the chosen numeric_col
    #    It includes N (count of non-null), missing, min, q25, median, q75, mean, max
    agg_dict = {
        numeric_col: [
            'count',       # Non-missing count
            missing_count, # Missing
            'min',
            q25,
            q50,
            q75,
            'mean',
            'max'
        ]
    }

    # 3) Perform groupby if group_by_cols is provided, else do a global summary
    if group_by_cols is not None:
        # Accept a single string or a list of strings
        if isinstance(group_by_cols, str):
            group_by_cols = [group_by_cols]
        summary = df.groupby(group_by_cols).agg(agg_dict)
    else:
        # No grouping => just aggregate the entire DataFrame
        summary = df.agg(agg_dict)

    # 4) The result is a multi-level column index. Flatten it.
    #    We'll get something like:
    #       (numeric_col, 'count'), (numeric_col, '<lambda>'), ...
    #    After flattening, rename the stats to a friendlier label.
    summary.columns = summary.columns.droplevel(0)  # drop the numeric_col level
    # summary now has columns like: ['count','missing','min','q25','median','q75','mean','max']

    # 5) Optionally, reorder columns in a nice sequence
    #    We'll define the exact ordering we want:
    desired_order = ['count','missing','min','q25','median','q75','mean','max']
    # Some columns might have <lambda> instead of 'missing' if the function name wasn't recognized
    # We can do a manual rename if needed.
    rename_map = {}
    for col in summary.columns:
        if '<lambda>' in col:
            rename_map[col] = 'missing'  # rename the lambda to 'missing'
    summary.rename(columns=rename_map, inplace=True)

    # Now reorder columns if they all exist
    existing_cols = [c for c in desired_order if c in summary.columns]
    summary = summary[existing_cols]  # reorder if possible

    # 6) If we had group_by_cols, reset_index so those become DataFrame columns
    if group_by_cols is not None:
        summary = summary.reset_index()

    # 7) Final step: rename for clarity, e.g. rename 'count' -> 'N' if desired
    rename_final = {
        'count': 'N'
    }
    summary.rename(columns=rename_final, inplace=True)

    return summary

def is_dose_within_range(row, outlier_dict):
    '''
    Check if med_dose_converted is within the outlier-configured range for this med_category.
    Parameters:
        row (pd.Series): A row from a DataFrame, must include 'med_category' and 'med_dose_converted'.
        outlier_dict (dict): Dictionary of min/max pairs from outlier_config.json.
    Returns:
        bool: True if the dose is within range or if med_category is not found, False otherwise.
    '''
    med_category = row['med_category']
    med_dose_converted = row['med_dose_converted']
    dose_range = outlier_dict.get(med_category, None)
    if dose_range is None:
        return False
    min_dose, max_dose = dose_range
    return min_dose <= med_dose_converted <= max_dose

def generate_table_one(final_df, filename):
    """
    Generate Table 1 from the input dataframe by merging patient and hospitalization data,
    selecting relevant columns, mapping race categories, and generating descriptive statistics.

    Parameters:
        final_df (pd.DataFrame): The input dataframe containing hospitalization data.
        filename (str): The name of the output file (without path).

    Returns:
        pd.DataFrame: The generated Table 1 as a dataframe.
    """
    # Load patient and hospitalization data
    patient = load_data('clif_patient')
    hospitalization = load_data('clif_hospitalization')

    # Ensure ID columns are strings
    hospitalization['hospitalization_id'] = hospitalization['hospitalization_id'].astype(str)
    patient['patient_id'] = patient['patient_id'].astype(str)

    # Remove duplicates
    patient = remove_duplicates(patient, ['patient_id'], 'patient')
    hospitalization = remove_duplicates(hospitalization, ['hospitalization_id'], 'hospitalization')

    # Select relevant columns
    columns_to_keep = [
        'hospitalization_id', 'encounter_block', 'recorded_date', 'recorded_hour', 'all_green',
        'patel_flag', 'team_flag', 'any_yellow_or_green_no_red', 'ne_calc_min', 
        'max_peep_set', 'min_fio2_set'
    ]
    
    final_df_table1 = final_df[columns_to_keep]

    # Merge with patient and hospitalization data
    final_df_table1 = pd.merge(final_df_table1, hospitalization, how='left', on='hospitalization_id')
    final_df_table1 = pd.merge(final_df_table1, patient, how='left', on='patient_id')

    # Map race column
    final_df_table1 = map_race_column(final_df_table1, 'race_category')

    # Define categorical and continuous variables
    categorical = ['sex_category', 'race_new', 'ethnicity_category']
    continuous = ['age_at_admission']

    # Include additional continuous variables if they exist in the dataframe
    additional_continuous = ['ne_calc_min', 'max_peep_set', 'min_fio2_set']
    continuous += [var for var in additional_continuous if var in final_df_table1.columns]

    # Define criteria-based subsets
    criteria_dict = {
        'Patel Criteria': 'patel_flag',
        'TEAM Criteria': 'team_flag',
        'Yellow Criteria': 'any_yellow_or_green_no_red',
        'Green Criteria': 'all_green'
    }

    # Create criteria-based subsets
    subsets = [final_df_table1.assign(Criteria='All Encounters')]
    for criteria, column in criteria_dict.items():
        subsets.append(final_df_table1[final_df_table1[column] == 1].assign(Criteria=criteria))

    # Combine all subsets
    combined_df = pd.concat(subsets, ignore_index=True)

    # Remove duplicates to ensure each hospitalization_id appears only once per criteria
    combined_df = combined_df.drop_duplicates(subset=['hospitalization_id', 'Criteria'])

    # Create TableOne
    table1 = TableOne(
        combined_df,
        columns=categorical + continuous,
        categorical=categorical,
        groupby='Criteria',
        pval=False,
        missing=False
    )

    # Convert TableOne object to DataFrame
    table1_df = table1.tableone.reset_index()

    # Remove 'Overall' column
    table1_check = table1_df.drop(columns=[('Grouped by Criteria', 'Overall')])
    # Rename the MultiIndex columns
    new_column_names = ['Characteristics', 'Category', 'All Encounters', 
                         'Patel Criteria', 'TEAM Criteria', 'Yellow Criteria', 'Green Criteria'] 
    table1_check.columns = new_column_names
    # Save to CSV
    # Construct the output path using the filename provided
    output_path = f'../output/final/{filename}_{helper["site_name"]}_{datetime.now().date()}.csv'
    table1_check.to_csv(output_path, index=False)
    print(f"TableOne saved to {output_path}")

    return table1_check

def generate_table_one_new(final_df, all_ids_w_outcome, filename):
    """
    Generate Table 1 including mortality statistics and SOFA components.
    """
    # Load patient and hospitalization data
    patient = load_data('clif_patient')
    hospitalization = load_data('clif_hospitalization')

    # Ensure ID columns are strings
    hospitalization['hospitalization_id'] = hospitalization['hospitalization_id'].astype(str)
    patient['patient_id'] = patient['patient_id'].astype(str)
    all_ids_w_outcome['hospitalization_id'] = all_ids_w_outcome['hospitalization_id'].astype(str)

    # Remove duplicates
    patient = remove_duplicates(patient, ['patient_id'], 'patient')
    hospitalization = remove_duplicates(hospitalization, ['hospitalization_id'], 'hospitalization')

    # Select relevant columns including SOFA components
    columns_to_keep = [
        'hospitalization_id', 'encounter_block', 'recorded_date', 'recorded_hour', 'all_green',
        'patel_flag', 'team_flag', 'any_yellow_or_green_no_red', 'ne_calc_min', 
        'max_peep_set', 'min_fio2_set',
        'sofa_cv_97', 'sofa_coag', 'sofa_renal', 'sofa_liver', 'sofa_resp', 'sofa_cns', 'sofa_total'  # Added SOFA components
    ]
    
    final_df_table1 = final_df[columns_to_keep]

    # Merge with patient, hospitalization, and mortality data
    final_df_table1 = pd.merge(final_df_table1, hospitalization, how='left', on='hospitalization_id')
    final_df_table1 = pd.merge(final_df_table1, patient, how='left', on='patient_id')
    final_df_table1 = pd.merge(
        final_df_table1, 
        all_ids_w_outcome[['hospitalization_id', 'is_dead']], 
        how='left', 
        on='hospitalization_id'
    )

    # Map race column
    final_df_table1 = map_race_column(final_df_table1, 'race_category')

    # Define categorical and continuous variables
    categorical = ['sex_category', 'race_new', 'ethnicity_category', 'is_dead']
    continuous = ['age_at_admission']

    # Add SOFA components to continuous variables
    sofa_components = ['sofa_cv_97', 'sofa_coag', 'sofa_renal', 'sofa_liver', 'sofa_resp', 'sofa_cns', 'sofa_total']
    continuous += sofa_components

    # Include additional continuous variables if they exist
    additional_continuous = ['ne_calc_min', 'max_peep_set', 'min_fio2_set']
    continuous += [var for var in additional_continuous if var in final_df_table1.columns]

    # Define criteria-based subsets
    criteria_dict = {
        'Patel Criteria': 'patel_flag',
        'TEAM Criteria': 'team_flag',
        'Yellow Criteria': 'any_yellow_or_green_no_red',
        'Green Criteria': 'all_green'
    }

    # First, let's print the counts for verification
    print("Counts before concatenation:")
    print(f"All Encounters: {len(final_df_table1)}")
    print(f"Patel Criteria (patel_flag=1): {len(final_df_table1[final_df_table1['patel_flag'] == 1])}")
    print(f"TEAM Criteria (team_flag=1): {len(final_df_table1[final_df_table1['team_flag'] == 1])}")
    print(f"Yellow Criteria (any_yellow_or_green_no_red=1): {len(final_df_table1[final_df_table1['any_yellow_or_green_no_red'] == 1])}")
    print(f"Green Criteria (all_green=1): {len(final_df_table1[final_df_table1['all_green'] == 1])}")

    all_encounters = final_df_table1.assign(Criteria='All Encounters')
    patel_subset = final_df_table1[final_df_table1['patel_flag'] == 1].assign(Criteria='Patel Criteria')
    team_subset = final_df_table1[final_df_table1['team_flag'] == 1].assign(Criteria='TEAM Criteria')
    yellow_subset = final_df_table1[final_df_table1['any_yellow_or_green_no_red'] == 1].assign(Criteria='Yellow Criteria')
    green_subset = final_df_table1[final_df_table1['all_green'] == 1].assign(Criteria='Green Criteria')

    print("\nCounts after subset creation:")
    print(f"All Encounters: {len(all_encounters)}")
    print(f"Patel Subset: {len(patel_subset)}")
    print(f"TEAM Subset: {len(team_subset)}")
    print(f"Yellow Subset: {len(yellow_subset)}")
    print(f"Green Subset: {len(green_subset)}")
    
    # Combine all subsets
    combined_df = pd.concat([
        all_encounters,
        patel_subset,
        team_subset,
        yellow_subset,
        green_subset
    ], ignore_index=True)

    # Remove duplicates to ensure each hospitalization_id appears only once per criteria
    combined_df = combined_df.drop_duplicates(subset=['hospitalization_id', 'Criteria'])

    # Create TableOne with nonnormal argument for SOFA components
    table1 = TableOne(
        combined_df,
        columns=categorical + continuous,
        categorical=categorical,
        groupby='Criteria',
        nonnormal=sofa_components,  # Specify SOFA components as nonnormal to get median and IQR
        pval=False,
        missing=False
    )

    # Convert TableOne object to DataFrame
    table1_df = table1.tableone.reset_index()

    # Remove 'Overall' column
    table1_check = table1_df.drop(columns=[('Grouped by Criteria', 'Overall')])
    
    # Rename the MultiIndex columns
    new_column_names = ['Characteristics', 'Category', 'All Encounters', 
                       'Patel Criteria', 'TEAM Criteria', 'Yellow Criteria', 'Green Criteria'] 
    table1_check.columns = new_column_names

    # Format mortality rows to show as n (%)
    mortality_rows = table1_check[table1_check['Characteristics'] == 'is_dead']
    for col in new_column_names[2:]:  # Skip 'Characteristics' and 'Category' columns
        total = combined_df[combined_df['Criteria'] == col]['is_dead'].count()
        deaths = combined_df[(combined_df['Criteria'] == col) & (combined_df['is_dead'] == True)]['is_dead'].count()
        percentage = (deaths / total * 100) if total > 0 else 0
        mortality_rows.loc[mortality_rows['Category'] == '1', col] = f"{deaths} ({percentage:.1f}%)"

    # Replace the original mortality rows
    table1_check.loc[table1_check['Characteristics'] == 'is_dead'] = mortality_rows

    # Rename rows for better clarity
    table1_check.loc[table1_check['Characteristics'] == 'is_dead', 'Characteristics'] = 'Mortality'
    table1_check.loc[table1_check['Category'] == '1', 'Category'] = ''

    # Save to CSV
    output_path = f'../output/final/{filename}_{helper["site_name"]}_{datetime.now().date()}.csv'
    table1_check.to_csv(output_path, index=False)
    print(f"TableOne saved to {output_path}")

    return table1_check

## meds dose conversion helpers

# Define medications and their unit conversion information
meds_list = [
    "norepinephrine", "epinephrine", "phenylephrine",
    "vasopressin", "dopamine", "angiotensin", "metaraminol", "dobutamine"
]

med_unit_info = {
    'norepinephrine': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['mcg/kg/min', 'mcg/kg/hr', 'mg/kg/hr', 'mcg/min', 'mg/hr'],
    },
    'epinephrine': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['mcg/kg/min', 'mcg/kg/hr', 'mg/kg/hr', 'mcg/min', 'mg/hr'],
    },
    'phenylephrine': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['mcg/kg/min', 'mcg/kg/hr', 'mg/kg/hr', 'mcg/min', 'mg/hr'],
    },
    'dopamine': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['mcg/kg/min', 'mcg/kg/hr', 'mg/kg/hr', 'mcg/min', 'mg/hr'],
    },
    'dobutamine': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['mcg/kg/min', 'mcg/kg/hr', 'mg/kg/hr', 'mcg/min', 'mg/hr'],
    },
    'metaraminol': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['mg/hr', 'mcg/min'],
    },
    'angiotensin': {
        'required_unit': 'mcg/kg/min',
        'acceptable_units': ['ng/kg/min', 'ng/kg/hr'],
    },
    'vasopressin': {
        'required_unit': 'units/min',
        'acceptable_units': ['units/min', 'units/hr', 'milliunits/min', 'milliunits/hr'],
    },
}

def check_dose_unit(row):
    med_category = row['med_category']
    med_dose_unit = row['med_dose_unit']
    # Check if med_category exists in med_unit_info
    if med_category in med_unit_info:
        # Check if med_dose_unit is in the acceptable units
        if med_dose_unit in med_unit_info[med_category]['acceptable_units']:
            return "Valid"
        else:
            return "Not an acceptable unit"
    else:
        return "Not a vasoactive"
    
def has_per_hour_or_min(unit):
    if pd.isnull(unit):
        return False
    unit = unit.lower()
    return '/hr' in unit or '/min' in unit

import numpy as np
import pandas as pd          # <- make sure this was imported

def get_conversion_factor(med_category: str,
                          med_dose_unit: str,
                          weight_kg: Union[float, None]) -> Union[float, None]:
    """
    Return a multiplier that converts *med_dose* from its current unit
    to the **required** unit for that medication.

    For units that need weight (mcg/min  → mcg/kg/min, mg/hr → mcg/kg/min …)
    we return *None* when weight_kg is missing so that the caller can decide
    what to do (keep the row with NaN, drop it, etc.).
    """
    med_info = med_unit_info.get(med_category)
    if med_info is None:
        return None                          # not a vaso we care about

    med_dose_unit = (med_dose_unit or "").lower()

    # ── helpers ───────────────────────────────────────────────
    has_weight = weight_kg is not None and not pd.isna(weight_kg)
    def w_needed(factor_if_known):
        return factor_if_known if has_weight else None
    # ──────────────────────────────────────────────────────────

    if med_category in ["norepinephrine", "epinephrine",
                        "phenylephrine", "dopamine",
                        "dobutamine", "metaraminol"]:
        if med_dose_unit == "mcg/kg/min": return 1.0
        elif med_dose_unit == "mcg/kg/hr": return 1/60
        elif med_dose_unit == "mg/kg/hr": return 1000/60
        elif med_dose_unit == "mcg/min": return w_needed(1/weight_kg)
        elif med_dose_unit == "mg/hr": return w_needed(1000/60/weight_kg)
    elif med_category == "angiotensin":
        if med_dose_unit == "ng/kg/min": return 1/1_000
        elif med_dose_unit == "ng/kg/hr": return 1/1_000/60
    elif med_category == "vasopressin":
        if med_dose_unit == "units/min": return 1.0
        elif med_dose_unit == "units/hr": return 1/60
        elif med_dose_unit == "milliunits/min": return 1/1_000
        elif med_dose_unit == "milliunits/hr": return 1/1_000/60

    return None                               # unit not recognised


def convert_dose(row: pd.Series) -> Union[float, None]:
    """
    Convert `row.med_dose` to the medication's **required** unit.

    Returns `np.nan` when:
    * the unit is unrecognised
    * weight is required but missing
    """
    factor = get_conversion_factor(
        row["med_category"],
        row["med_dose_unit"],
        row["weight_kg"]
    )
    return np.nan if factor is None else round(row["med_dose"] * factor, 5)


def categorize_device(row):
    if pd.notna(row['device_category']):
        return row['device_category']
    elif row['mode_category'] in ["simv", "pressure-regulated volume control", "assist control-volume control"]:
        return "vent"
    elif pd.isna(row['device_category']) and row['fio2_set'] == 0.21 and pd.isna(row['lpm_set']) and pd.isna(row['peep_set']) and pd.isna(row['tidal_volume_set']):
        return "room air"
    elif pd.isna(row['device_category']) and pd.isna(row['fio2_set']) and row['lpm_set'] == 0 and pd.isna(row['peep_set']) and pd.isna(row['tidal_volume_set']):
        return "room air"
    elif pd.isna(row['device_category']) and pd.isna(row['fio2_set']) and (0 < row['lpm_set'] <= 20) and pd.isna(row['peep_set']) and pd.isna(row['tidal_volume_set']):
        return "nasal cannula"
    elif pd.isna(row['device_category']) and pd.isna(row['fio2_set']) and row['lpm_set'] > 20 and pd.isna(row['peep_set']) and pd.isna(row['tidal_volume_set']):
        return "high flow nc"
    elif row['device_category'] == "nasal cannula" and pd.isna(row['fio2_set']) and row['lpm_set'] > 20:
        return "high flow nc"
    else:
        return row['device_category']  # Keep original value if no condition is met

# Try to fill in FiO2 based on other values    
def refill_fio2(row):
    if pd.notna(row['fio2_set']):
        return row['fio2_set']/100
    elif pd.isna(row['fio2_set']) and row['device_category'] == "room air":
        return 0.21 
    elif pd.isna(row['fio2_set']) and row['device_category'] == "nasal cannula" and pd.notna(row['lpm_set']):
        return (0.24 + (0.04 * row['lpm_set'])) 
    else:
        return np.nan

def merge_multiple_dfs(*dfs, on=None, how='outer'):
    """
    Merge multiple DataFrames on specified columns.
    Args:
        *dfs: Variable number of DataFrames to merge
        on: Column(s) to merge on
        how: Type of merge to perform
    Returns:
        Merged DataFrame
    """
    return reduce(lambda left, right: pd.merge(left, right, on=on, how=how), dfs)

# Example usage:
# dose_pivot = merge_multiple_dfs(dose_pivot_min, dose_pivot_max, dose_pivot_first, dose_pivot_last, 
#                               on=['encounter_block', 'recorded_date', 'recorded_hour'], 
#                               how='outer')


# def build_meds_hourly_scaffold(
#     meds_df: pd.DataFrame,
#     *,
#     id_col: str = "encounter_block",
#     ids=None,
#     timestamp_col: str = "admin_dttm",
#     site_tz: str = helper['timezone'] ,          # ← local zone you want in the result
# ) -> pd.DataFrame:
#     """
#     For every encounter block create a *single* row for every LOCAL hour
#     from the first to the last observation (inclusive).

#     Parameters
#     ----------
#     meds_df : DataFrame  - must contain `id_col` and `timestamp_col`
#     ids     : iterable   - optional list of blocks to keep
#     site_tz : str        - Olson tz name for the local timezone wanted
#                          - in the output (e.g. 'US/Central')

#     Returns
#     -------
#     DataFrame with columns
#         id_col · recorded_date · recorded_hour
#     (no duplicates).
#     """

#     # ── 0 · optional filtering ─────────────────────────────────────────
#     if ids is not None:
#         meds_df = meds_df.loc[meds_df[id_col].isin(ids)].copy()
#     if meds_df.empty:
#         raise ValueError("After filtering no rows remain.")

#     # ensure timezone‑aware UTC for safe arithmetic
#     meds_df = meds_df[[id_col, timestamp_col]].copy()
#     meds_df[timestamp_col] = pd.to_datetime(meds_df[timestamp_col], utc=True)

#     # drop exact‑timestamp duplicates up‑front (keep first)
#     meds_df = meds_df.drop_duplicates(subset=[id_col, timestamp_col],
#                                       keep="first")

#     # ── 1 · build the UTC scaffold ─────────────────────────────────────
#     scaffolds = []
#     for blk, g in meds_df.groupby(id_col, sort=False):
#         start = g[timestamp_col].min().floor("h")
#         end   = g[timestamp_col].max().floor("h")       # SAME hour as last obs
#         hrs   = pd.date_range(start, end, freq="h", tz="UTC")
#         scaffolds.append(pd.DataFrame({id_col: blk, timestamp_col: hrs}))

#     scaffold = pd.concat(scaffolds, ignore_index=True)

#     # ── 2 · merge scaffold ←→ original rows (left join) ────────────────
#     out = (scaffold
#            .merge(meds_df, on=[id_col, timestamp_col], how="left")
#            .sort_values([id_col, timestamp_col])
#            .reset_index(drop=True))
#     out[timestamp_col] = pd.to_datetime(out[timestamp_col], utc=True)
#     # ── 3 · convert to LOCAL time & derive date + hour ─────────────────
#     out["local_time"]   = out[timestamp_col].dt.tz_convert(site_tz)
#     out["recorded_date"] = out["local_time"].dt.date
#     out["recorded_hour"] = out["local_time"].dt.hour

#     # ── 4 · drop the duplicate LOCAL hour created by DST fall‑back ────
#     out = (out
#            .drop_duplicates(subset=[id_col, "recorded_date", "recorded_hour"],
#                             keep="first")
#            .loc[:, [id_col, "recorded_date", "recorded_hour"]]
#            .reset_index(drop=True))

#     return out

def build_meds_hourly_scaffold(
        meds_df: pd.DataFrame,
        *,
        id_col: str = "encounter_block",
        ids=None,
        timestamp_col: str = "admin_dttm",
        site_tz: str = helper["timezone"]          # e.g. "US/Central"
) -> pd.DataFrame:
    # ── 0 · filter ------------------------------------------------------
    if ids is not None:
        meds_df = meds_df.loc[meds_df[id_col].isin(ids)].copy()
    if meds_df.empty:
        raise ValueError("After filtering no rows remain.")

    # ── 1 · ensure tz‑aware in the requested local zone ----------------
    ts_local = pd.to_datetime(meds_df[timestamp_col])
    if ts_local.dt.tz is None:
        ts_local = ts_local.dt.tz_localize(site_tz, ambiguous="NaT",
                                           nonexistent="shift_forward")
    else:
        ts_local = ts_local.dt.tz_convert(site_tz)

    meds_df = meds_df[[id_col]].copy()
    meds_df["local_ts"] = ts_local
    meds_df = meds_df.drop_duplicates([id_col, "local_ts"])

    # ── 2 · scaffold (rounding done in UTC → no ambiguity) --------------
    scaffolds = []
    for blk, g in meds_df.groupby(id_col, sort=False):
        # convert to UTC just for min/max/floor
        utc = g["local_ts"].dt.tz_convert("UTC")
        start_utc = utc.min().floor("h")
        end_utc   = utc.max().floor("h")
        hrs_utc   = pd.date_range(start_utc, end_utc, freq="h", tz="UTC")

        hrs_local = hrs_utc.tz_convert(site_tz)   # back to local zone
        scaffolds.append(pd.DataFrame({id_col: blk, "local_ts": hrs_local}))

    scaffold = pd.concat(scaffolds, ignore_index=True)

    # ── 3 · merge scaffold ←→ original rows -----------------------------
    out = (scaffold
           .merge(meds_df, on=[id_col, "local_ts"], how="left")
           .sort_values([id_col, "local_ts"])
           .reset_index(drop=True))

    # ── 4 · derive date/hour & drop duplicate local hours ---------------
    out["recorded_date"] = out["local_ts"].dt.date
    out["recorded_hour"] = out["local_ts"].dt.hour

    out = out.drop_duplicates([id_col, "recorded_date", "recorded_hour"],
                              keep="first")

    return (out.loc[:, [id_col, "recorded_date", "recorded_hour"]]
               .sort_values([id_col, "recorded_date", "recorded_hour"])
               .reset_index(drop=True))




# def extend_hourly_dataset(base_df, addon_df, merge_cols):
#     """
#     Extend `base_df` with additional rows from `addon_df` beyond the last hour recorded per encounter_block.
    
#     Parameters
#     ----------
#     base_df : pd.DataFrame
#         Main dataset that contains all expected hours.
#     addon_df : pd.DataFrame
#         Dataset with potentially additional rows that need to be appended after the last timestamp in base_df.
#     merge_cols : list
#         Columns to join on, usually: ['encounter_block', 'recorded_date', 'recorded_hour']
    
#     Returns
#     -------
#     pd.DataFrame
#         Combined DataFrame with original base rows + extra addon rows after the last timepoint in base.
#     """

#     # Step 1: Reconstruct timestamps
#     base_df = base_df.copy()
#     addon_df = addon_df.copy()
    
#     base_df['recorded_dttm'] = pd.to_datetime(base_df['recorded_date']) + pd.to_timedelta(base_df['recorded_hour'], unit='h')
#     addon_df['recorded_dttm'] = pd.to_datetime(addon_df['recorded_date']) + pd.to_timedelta(addon_df['recorded_hour'], unit='h')

#     # Step 2: Merge addon onto base
#     merged = pd.merge(base_df, addon_df.drop(columns='recorded_dttm', errors='ignore'), on=merge_cols, how='left')

#     # Step 3: Get last recorded_dttm per encounter_block
#     max_times = base_df.groupby('encounter_block')['recorded_dttm'].max().reset_index(name='max_seq_dttm')

#     # Step 4: Get extra rows from addon_df
#     extra_candidates = pd.merge(addon_df, max_times, on='encounter_block', how='left')
#     extra_rows = extra_candidates[extra_candidates['recorded_dttm'] > extra_candidates['max_seq_dttm']].drop(
#         columns=['recorded_dttm', 'max_seq_dttm']
#     )

#     # Step 5: Combine base + extra
#     combined_df = pd.concat([merged, extra_rows], ignore_index=True)

#     # Step 6: Clean up
#     combined_df = combined_df.drop(columns='recorded_dttm', errors='ignore')
#     combined_df = combined_df.sort_values(merge_cols).reset_index(drop=True)

#     return combined_df

from datetime import timedelta
import numpy as np
import pandas as pd

def extend_hourly_dataset(base_df, addon_df, merge_cols):
    """
    Extend `base_df` with extra rows from `addon_df` beyond the last hour per encounter_block,
    preserving all columns from both input DataFrames and filling any time gaps.
    
    Parameters
    ----------
    base_df : pd.DataFrame
        Main dataset with hourly scaffold (e.g., hourly_seq_block).
    addon_df : pd.DataFrame
        Dataset with additional data (e.g., hourly_vent_block).
    merge_cols : list of str
        Columns to join on (typically ['encounter_block', 'recorded_date', 'recorded_hour']).
    
    Returns
    -------
    pd.DataFrame
        Combined DataFrame with merged values, extra rows, gap-filled hours,
        and time_from_vent variables added.
    """

    base_df = base_df.copy()
    addon_df = addon_df.copy()

    # ── 1. Add timestamp columns for comparison ────────────────────────
    base_df['recorded_dttm'] = pd.to_datetime(base_df['recorded_date']) + pd.to_timedelta(base_df['recorded_hour'], unit='h')
    addon_df['recorded_dttm'] = pd.to_datetime(addon_df['recorded_date']) + pd.to_timedelta(addon_df['recorded_hour'], unit='h')

    # ── 2. Get last recorded time per encounter ────────────────────────
    max_times = (
        base_df.groupby('encounter_block')['recorded_dttm']
        .max().reset_index()
        .rename(columns={'recorded_dttm': 'max_seq_dttm'})
    )

    # ── 3. Find extra addon rows after last scaffold time ──────────────
    addon_with_max = pd.merge(addon_df, max_times, on='encounter_block', how='left')
    extra_rows = addon_with_max[addon_with_max['recorded_dttm'] > addon_with_max['max_seq_dttm']].copy()

    # ── 4. Fill gaps between scaffold and first extra row ─────────────
    gap_rows = []
    for enc_id, group in extra_rows.groupby('encounter_block'):
        max_time = pd.to_datetime(
            max_times.loc[max_times['encounter_block'] == enc_id, 'max_seq_dttm'].values[0]
        )
        first_extra_time = group['recorded_dttm'].min()

        if first_extra_time <= max_time + timedelta(hours=1):
            continue

        gap_range = pd.date_range(start=max_time + timedelta(hours=1), end=first_extra_time - timedelta(hours=1), freq='H')
        for dt in gap_range:
            gap_rows.append({
                'encounter_block': enc_id,
                'recorded_date': dt.date(),
                'recorded_hour': dt.hour,
                'recorded_dttm': dt
            })

    gap_df = pd.DataFrame(gap_rows)

    # ── 5. Ensure gap_df has all columns from base and addon ──────────
    full_cols = list(set(base_df.columns).union(set(addon_df.columns)))
    for col in full_cols:
        if col not in gap_df.columns:
            gap_df[col] = np.nan
    gap_df = gap_df[full_cols]

    # ── 6. Merge scaffold and addon ───────────────────────────────────
    scaffold_merged = pd.merge(
        base_df.drop(columns='recorded_dttm', errors='ignore'),
        addon_df.drop(columns='recorded_dttm', errors='ignore'),
        on=merge_cols,
        how='left'
    )

    # ── 7. Combine scaffold + gaps + extras ───────────────────────────
    combined_df = pd.concat(
        [scaffold_merged, gap_df.drop(columns=['recorded_dttm'], errors='ignore'), extra_rows.drop(columns=['recorded_dttm', 'max_seq_dttm'], errors='ignore')],
        ignore_index=True
    )

    # ── 8. Time from vent ─────────────────────────────────────────────
    combined_df = combined_df.sort_values(by=merge_cols).reset_index(drop=True)
    combined_df['time_from_vent'] = combined_df.groupby('encounter_block').cumcount()
    combined_df['time_from_vent_adjusted'] = np.where(
        combined_df['time_from_vent'] < 4, -1, combined_df['time_from_vent'] - 4
    )

    # ── 9. Column reordering ──────────────────────────────────────────
    id_cols = [col for col in combined_df.columns if col.endswith('id') and col not in ['encounter_block']]
    key_cols = ['encounter_block', 'recorded_date', 'recorded_hour', 'time_from_vent', 'time_from_vent_adjusted']
    other_cols = [col for col in combined_df.columns if col not in id_cols + key_cols]
    combined_df = combined_df[id_cols + key_cols + other_cols]

    combined_df['encounter_block'] = combined_df['encounter_block'].astype(int)
    combined_df['recorded_hour']   = combined_df['recorded_hour'].astype(int)

    return combined_df