"""
Created on Wed May 21 15:16:13 2025

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

This script is designed to run the function created in kilosort_automation.py
"""

import kilosort_automation as ksa

ksa.automate_kilosort(
    path = 'C:\\Users\\Z390\\Documents\\Scripts\\Python\\Kilosort-4_additional_code\\automate_kilosort',
    feeder = 'feeder_for_kilosort.xlsx', settings_file = 'kilosort_settings.json')