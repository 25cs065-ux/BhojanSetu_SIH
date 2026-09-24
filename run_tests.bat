@echo off
REM BhojanSetu — Feature 7-10 Test Runner
REM Run this script after installing Python and requirements.txt

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Running Feature 7 (Production Planner) tests...
python -m pytest tests/test_production_planner.py -v

echo.
echo Running all module tests (unit + integration)...
python tests/run_all_tests.py

echo.
echo Running integration test...
python tests/test_integration.py

echo.
echo Done.
pause
