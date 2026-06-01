%SummarizeAllEvents("D:\HOF DATA\ACTIVE DATA")
%EventsVisualizer("D:\HOF DATA\ACTIVE DATA", "D:\HOF DATA\ACTIVE DATA\PYTHON_UI_DATA")
%NeuroScope_Generator_SingleFile('D:\HOF DATA\ACTIVE DATA\PYTHON_UI_DATA\J2_PRECON2_SP_091325.mat', 'D:\HOF DATA\ACTIVE DATA\PYTHON_UI_DATA\Pre Generated Images', true)

%Extract_First_Combo()
%Plot_Connectivity_Synthetic_Masterclass("D:\HOF DATA\ACTIVE DATA\PYTHON_UI_DATA\J2_PRECON2_SP_091325_FirstHTLT.mat")
%Plot_Coherence_Modulation_Masterclass()
Generate_Connectivity_Dashboard()