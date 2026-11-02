function outmat = CFCMatrix(string,repnum)
goodstuff = max(1,numel(string)-string);
string = strcat(string(goodstuff:end),',');
outmat = repmat(string,1,repnum);
cleaner = strlength(outmat);
outmat = extractBefore(outmat,cleaner);
outmat = split(outmat,",");
end
