This python script will prompt you for a Source folder and a destination.
It will then create a "Clone" of the source folder, however all the files are essecially text files that only contain the CRC32,MD5,SHA1 hashes of the files that were copied.

WHY?

This script was created because i had a large library i did not want to potentially destroy while testing another project.
The other project needed to be able to hash the files so this seems like a simple solution. Will it come in handy to anyone else? 
Who knows... enjoy.

if there are files you wish to actually clone and not have a sudo-version on edit the 

EXCEPTION_FILES = {"_info.txt", "gamelist.xml"}

line in the script for what you need.
