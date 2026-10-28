````powershell
@'
# Execution Steps

## 1. Windows (VS Code + PowerShell)

Install Python 3.10+ and VS Code, then open the project folder in VS Code.

```powershell
# Check the installed Python version.
python --version

# Run all unit tests and display detailed results.
python -m unittest discover -s tests -v

# Generate synthetic datasets using the specified seed and scale.
python -m insurance_workflow.generator --output data --seed 20261022 --scale 1

# Validate the generated datasets and business rules.
python -m insurance_workflow.validator --data data

# Create a SQLite database from the project's database setup scripts.
python .\build_database.py --output data\insurance_fresh.db

# Run all unit tests again to verify the project.
python -m unittest discover -s tests -v

# Check whether repeated executions produce consistent results.
python .\scripts\check_reproducibility.py
````

## 2. Apple macOS (VS Code + Terminal)

Install Python 3.10+ and VS Code, then open the project folder in VS Code.

```bash
# Check the installed Python version.
python3 --version

# Run all unit tests and display detailed results.
python3 -m unittest discover -s tests -v

# Generate synthetic datasets using the specified seed and scale.
python3 -m insurance_workflow.generator --output data --seed 20261022 --scale 1

# Validate the generated datasets and business rules.
python3 -m insurance_workflow.validator --data data

# Create a SQLite database from the project's database setup scripts.
python3 build_database.py --output data/insurance_fresh.db

# Run all unit tests again to verify the project.
python3 -m unittest discover -s tests -v

# Check whether repeated executions produce consistent results.
python3 scripts/check_reproducibility.py
```

'@ | Set-Content README.md -Encoding utf8

````
