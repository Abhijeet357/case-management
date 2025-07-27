import os
import sys

# Check if we can find the cases directory
cases_dir = 'C:\\Users\\hp\\Documents\\case_management_system\\cases'

print("Checking cases directory...")
print(f"Does cases directory exist? {os.path.exists(cases_dir)}")

if os.path.exists(cases_dir):
    # List all Python files in cases directory
    print("\nPython files in cases directory:")
    for file in os.listdir(cases_dir):
        if file.endswith('.py'):
            print(f"  - {file}")

    # Check admin.py content
    admin_path = os.path.join(cases_dir, 'admin.py')
    if os.path.exists(admin_path):
        print(f"\nFirst 15 lines of {admin_path}:")
        with open(admin_path, 'r') as f:
            for i, line in enumerate(f):
                if i < 15:
                    print(f"{i+1}: {line.rstrip()}")
                else:
                    break

# Save this as a script to run
print("\n\nSave this script as check_admin.py in your project root and run it with:")
print("python check_admin.py")
