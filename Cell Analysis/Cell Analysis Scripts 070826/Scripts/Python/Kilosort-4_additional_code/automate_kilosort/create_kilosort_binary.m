function []=create_kilosort_binary (filedir, xlsxfilename, probeName, varargin)
% Author: Skyler Younger skyler.younger@uvm.edu
% Use feedersheet to locate high-density probe recording files and create
% binary files from their .ncs files to be used in Kilosort. Will
% additionally output an excel feeder sheet to be used to run Kilosort
% on all binary files created here.
% Inputs:
% filedir: string containing pathway to the feeder sheet
% xlsxfilename: string with the name of the .xlsx feeder sheet file to be
%   read
% probeName: string with name of probe to be used in perpl_NLX2Binary
%   function

cd (filedir); % Set current directory
% read excel feedersheet
[data,txt] =  xlsread('binary_kilosort_feeder.xlsx');
% I guess we are removing the top two filler rows instead of just not 
% including them with the next two lines? I copied this from elsewhere
qqq=txt(1:2,:);
txt(1:2,:)=[];
% Not sure how else to do this, but I am setting up a way to append the
% output paths in subsequent rows rather than columns. Feel free to fix 
% this if you know how to do it better.
binary_feeder = ["filler";"filler"];
binary_filler = ["1"];

for feeder_index = 1:size(data,1);
    path_ncs = txt{feeder_index,2}; % Get the filepath from the feeder sheet
    % Create the string name for the binary file
    path_output = append(path_ncs,'\binary'); 
    
    % If statement checks to see if the binary file already exists
    % If the binary file exists, skip this file
    if isdir(path_output) == true;
        % Add the filepath to the binary file to the eventual excel output
        binary_feeder(feeder_index) = convertCharsToStrings(path_output);
        binary_filler(feeder_index) = "1";

    % If the binary file does not exist, run the binary creation function
    elseif isdir(path_output) == false;
        % Add the filepath to the binary file to the eventual excel output
        binary_feeder(feeder_index) = path_output;
        binary_filler(feeder_index) = "1";
        
        % Create a folder for the binary file
        mkdir(path_output);
        
        % Create binary file in new folder
        % Example of binary creation function: perpl_NLX2Binary(
        %   'D:\PTEN\PTEN\M34_ptenblind\m34s5jun10\2024-06-10_14-45-34',
        %   'D:\PTEN\PTEN\M34_ptenblind\m34s5jun10\2024-06-10_14-45-34\binary', 
        %   'CSC')
        perpl_NLX2Binary(path_ncs,path_output,probeName);
    end;

end;
feeder_table = table(binary_feeder);
writetable(feeder_table,'feeder_for_kilosort.xlsx','WriteVariableNames',false);
