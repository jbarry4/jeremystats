"""
Created on Wed May 21 14:38:51 2025

@author: Rain Younger

⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣤⣄⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⣿⣿⣿⣿⣿⣦⡀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⣠⣾⣿⣿⣶⣄⠀⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣾⣿⣿⣿⣿⣿⣿⣷⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⣀⣀⡀⠀⠀⠀
⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⡀⠀
⠀⢠⣶⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⠀
⠀⢾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⠀
⠀⠈⠿⣿⣿⡿⠋⠈⠻⣿⣿⣿⣿⡿⠟⠁⠀⠙⠿⠿⠛⠁⠙⠻⠿⠿⠟⠁⠀⠀
⠀⠀⠀⠀⣠⡀⠀⠀⢦⡄⠉⠉⣁⠀⠀⠀⠀⠀⠀⠰⡆⠀⠀⢰⣆⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠸⠇⠀⠀⠈⠀⠀⠀⠛⠀⠀⠀⢹⡇⠀⠀⠀⠀⠀⠀⠛⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⡀⠀⠀⢰⡄⠀⠀⣀⠀⠀⠈⠛⠀⠀⢰⣧⠀⠀⠀⣀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠸⣷⠀⠀⠈⠉⠀⠀⢻⡇⠀⠀⠀⡀⠀⠀⠉⠀⠀⠀⢻⡄⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠛⠂⠀⠀⢠⡄⠀⠈⠟⠀⠀⠀⢿⠀⠀⠀⣤⠀⠀⠈⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⣠⡀⠀⠀⠃⠀⠀⠀⣀⠀⠀⠘⠃⠀⠀⠉⠀⠀⠀⢰⡄⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠘⠃⠀⠀⠀⠀⠀⠀⠛⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠓⠀⠀

This function is designed to automate the kilosort process and to be used in
tandem with the MATLAB code used to automate the creation of binary files.
"""

import pandas as pd
import os as os
import json as json
from kilosort import run_kilosort


def automate_kilosort(path,feeder,settings_file,probe_name='probe_config.prb',
                      remove_channels=[7,37,58], invert_bool=True):
    """
    Known bug: Kilosort will crash if the number of clusters is less than 6. 
    You will need to rerun this function each time this occurs because I do
    not know how to fix this issue. You will not need to change the feeder 
    sheet because the if-statements will recognize a folder has been created 
    in an attempt to run kilosort on the binary file which crashed. Just 
    run the function again without changing anything.
    
    Parameters
    ----------
    path : str
        This path is meant to be the working directory where the feeder sheet
        is located.
    feeder : str
        Name of the feeder sheet .xlsx file.
    settings_file : str
        Name of the .json file exported from kilosort with all the kilosort
        settings saved.
    probe_name : str, optional
        Name of the file containing settings for the probe used for recording.
        The default is 'probe_config.prb'.
    remove_channels : list of ints, optional
        List of channels to be excluded from the kilosort analysis. Please 
        remember that whil the .ncs files are named 1-64, kilosort utilizes
        python, so the indexing will result in channel numbers 0-63. The 
        default is [7,37,58].
    invert_bool: bool
        State whether the data should be inverted when processing via Kilosort

    Returns nothing
    -------
    The end result of this function should be a kilosort file for each of the
    recording sessions/binary files in the feeder sheet.

    """
    
    # Change the working directory to the folder in which the feeder sheet is
    # located
    os.chdir(path)
    
    # Create a dataframe from the feeder sheet and convert the dataframe into
    # a numpy array
    df = pd.read_excel(feeder)
    feeder_sheet = df.to_numpy()
    
    # Extract the necessary settings from the .json file into a dictionary 
    # titled settings_main
    with open(settings_file) as settings_txt:
        settings = json.loads(settings_txt.read())
        settings_main = settings['main'] # I am not sure when the other 
        # parts of the settings would be important, but 'main' seems to be all
        # that is needed
        
    # Run kilosort on every binary file in the feeder sheet
    for feeder_path in feeder_sheet:
        # convert the full path to the binary file into a str
        data_path = str(feeder_path[0]) 
        # Extract the Th_learned value
        tl = str(settings['main']['Th_learned'])
        tl = tl[0]
        # Extract the Th_universal value
        tu = str(settings['main']['Th_universal'])
        tu = tu[0]
        # Extract the fs value
        fs = str(settings['main']['fs'])
        # Create a path for a results directory utilizing the tl & tu values
        results_dir = data_path + '\\kilosort_tl' + tl + '_tu' + tu + '_fs' + fs + 'invert_' + str(invert_bool)
        
        # If kilosort has not been run at these tl & tu values, create a new
        # directory for the results and run kilosort
        if os.path.isdir(results_dir)==False:
            
            os.mkdir(results_dir) # Create the results directory
            
            # Run kilosort using the following settings. 
            run_kilosort(settings=settings_main,probe_name=probe_name,
                         filename=f'{data_path}\\CSC_Raw.dat',data_dir=data_path,
                         results_dir=results_dir,save_preprocessed_copy=True,
                         bad_channels=remove_channels,verbose_log=True,
                         invert_sign=invert_bool)
        
        # If kilosort has already been run or attempted to have been run on a
        # binary file, skip that binary file and move onto the next one
        else: 
            continue
        
        