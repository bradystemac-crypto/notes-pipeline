@echo off
cd C:\Users\brady\OneDrive\Documents\notes-pipeline
echo Starting Notes Pipeline...
pause
set /p pdf="PDF path: "
set /p course="Course: "
set /p topic="Topic: "
python main.py "%pdf%" "%course%" "%topic%"
pause