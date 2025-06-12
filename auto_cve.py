# Copyright (c) Microsoft Corporation.
# Licensed: Free to copy and distribute.
# Author: Aninda Pradhan
# Email: v-anipradhan@microsoft.com
# Version: 1.0
# Date: 06/12/2025

# This script automates the process of downloading, extracting, and patching source code for CVE fixes based on a spec file.
# It automates the steps mentioned in https://github.com/microsoft/azurelinux/blob/fe33b5ac4a569e18d42c56eb9e9258f2582782d9/toolkit/docs/CVE/CVE-Quickstart-Guide.md
# It allows users to apply new patches and create patch files for CVE fixes.
# It provides the option to verify if the patches mentioned in the spec file apply cleanly, which can be used to verify before making a final commit.
# It inserts the upstream patch reference in the patch file for better tracking of changes.



import re
import os
import subprocess
import shutil

def extract_source0_filename(spec_content):
    macros = dict(re.findall(r'^%define\s+(\w+)\s+([^\n]+)', spec_content, re.MULTILINE))
    name_match = re.search(r'^Name:\s+([^\s]+)', spec_content, re.MULTILINE)
    if name_match:
        macros['name'] = name_match.group(1)
    version_match = re.search(r'^Version:\s+([^\s]+)', spec_content, re.MULTILINE)
    if version_match:
        macros['version'] = version_match.group(1)

    source0_match = re.search(r'^Source0:\s+([^\s]+)', spec_content, re.MULTILINE)
    if not source0_match:
        return None, None

    source0 = source0_match.group(1)
    source0_resolved = re.sub(r'%\{(\w+)\}', lambda m: macros.get(m.group(1), m.group(0)), source0)
    parts = source0_resolved.rsplit('/', 1)
    return parts[0], parts[1]

def extract_patches(spec_content):
    return re.findall(r'^Patch\d+:\s+([^\s]+)', spec_content, re.MULTILINE)

def apply_patches(patches, spec_path):
    for patch in patches:
        patch_path = os.path.join(os.path.dirname(spec_path), patch)
        subprocess.run(["patch", "-p1", "--fuzz=0", "-i", patch_path], check=True)

def prompt_delete_directory(directory):
    if os.path.exists(directory):
        response = input(f"\033[1;33mDirectory '{directory}' already exists. Do you want to delete it and continue? (y-[yes]/n-[no]):\033[0m ").strip().lower()
        if response in ['yes', 'y']:
            shutil.rmtree(directory)
        else:
            print("\033[1;31m❌ Operation aborted by user.\033[0m")
            exit(1)

def insert_upstream_reference(patch_file_path, patch_url):
    with open(patch_file_path, 'r') as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if line.startswith('Subject:'):
            lines.insert(i + 1, f'Upstream Patch Reference: {patch_url}\n')
            break

    with open(patch_file_path, 'w') as f:
        f.writelines(lines)

def main():
    spec_path = input("\033[1;33mEnter the path to the spec file:\033[0m ")

    print("\nChoose an option:")
    print("a) Just want to verify if the patches mentioned in the spec file apply cleanly?")
    print("b) Apply the existing patches mentioned in the spec file and do an initial commit if successful")
    choice = input("\033[1;33mEnter your choice (a/b):\033[0m ").strip().lower()

    try:
        with open(spec_path, "r") as f:
            spec_text = f.read()

        path, filename = extract_source0_filename(spec_text)
        patches = extract_patches(spec_text)

        if path and filename:
            pkg_name = filename.rsplit('.', 2)[0]

            if choice == 'a':
                test_dir = f"cve-test-for-{pkg_name}"
                prompt_delete_directory(test_dir)
                os.makedirs(test_dir, exist_ok=True)
                download_url = f"https://azurelinuxsrcstorage.blob.core.windows.net/sources/core/{filename}"
                subprocess.run(["wget", download_url, "-P", test_dir], check=True)
                tarball_path = os.path.join(test_dir, filename)
                subprocess.run(["tar", "-xf", tarball_path, "-C", test_dir], check=True)
                pkg_path = os.path.join(test_dir, pkg_name)
                os.chdir(pkg_path)

                if patches:
                    try:
                        apply_patches(patches, spec_path)
                        print(f"\033[1;32m✅ All patches applied cleanly.\033[0m")
                    except subprocess.CalledProcessError:
                        print(f"\033[1;31m❌ One or more patches failed to apply.\033[0m")
                else:
                    print(f"\033[1;31m❌ No patches found in the spec file.\033[0m")

            elif choice == 'b':
                cve_number = input("\033[1;33mEnter the CVE number you are working on, currently limited to single CVE (format: CVE-YYYY-NNNNNN):\033[0m ")
                version = input("\033[1;33mIs this patch for version 2.0 or 3.0? Enter 2.0 or 3.0:\033[0m ").strip()
                base_dir = os.path.join(cve_number, version)
                prompt_delete_directory(base_dir)
                os.makedirs(base_dir, exist_ok=True)
                download_url = f"https://azurelinuxsrcstorage.blob.core.windows.net/sources/core/{filename}"
                subprocess.run(["wget", download_url, "-P", base_dir], check=True)
                tarball_path = os.path.join(base_dir, filename)
                subprocess.run(["tar", "-xf", tarball_path, "-C", base_dir], check=True)
                pkg_path = os.path.join(base_dir, pkg_name)
                os.chdir(pkg_path)

                subprocess.run(["git", "init"], check=True)
                subprocess.run(["git", "add", "."], check=True)
                subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

                if patches:
                    apply_patches(patches, spec_path)
                    subprocess.run(["git", "add", "-u"], check=True)
                    subprocess.run(["git", "commit", "-m", "In pace with azl"], check=True)
                    print(f"\033[1;32m✅ Done: {filename} downloaded, extracted, patched, and committed in Git repo under {base_dir}/\033[0m")
                else:
                    print(f"\033[1;31m❌ No patches found in the spec file.\033[0m")
                    print(f"\033[1;32m✅ Done: {filename} downloaded, extracted, and did Initial commit/\033[0m")

                print("\nWould you like to apply a new patch and create a patch file?")
                proceed_c = input("\033[1;33mEnter y to proceed or n to exit:\033[0m ").strip().lower()
                if proceed_c == 'y':
                    new_patch_url = input("\033[1;33mEnter the new CVE patch URL (e.g., https://github.com/<commit-id>.patch):\033[0m ").strip()
                    original_patch_filename = f"{cve_number}_original.patch"
                    original_patch_path = os.path.abspath(os.path.join("..", "..", original_patch_filename))
                    subprocess.run(["wget", new_patch_url, "-O", original_patch_path], check=True)

                    try:
                        subprocess.run(["patch", "-p1", "--fuzz=0", "-i", original_patch_path], check=True)

                        show_diff = input("\033[1;33mDo you want to see the git diff before creating the patch file? (y/n):\033[0m ").strip().lower()
                        if show_diff == 'y':
                            subprocess.run(["git", "diff"])

                        subprocess.run(["git", "add", "-u"], check=True)
                        subprocess.run(["git", "commit", "-m", f"Address {cve_number}"], check=True)
                        subprocess.run(["git", "format-patch", "-1", "HEAD"], check=True)

                        for file in os.listdir("."):
                            if file.endswith(".patch") and not file.startswith(cve_number):
                                os.rename(file, f"{cve_number}.patch")
                                insert_upstream_reference(f"{cve_number}.patch", new_patch_url)
                                break
                        shutil.copy(f"{cve_number}.patch", os.path.dirname(spec_path))
                        print(f"\033[1;32m✅ New patch {cve_number}.patch created and applied.\033[0m")
                    except subprocess.CalledProcessError:
                        print(f"\033[1;31m❌ New patch failed to apply. Reverting to original state.\033[0m")
                        subprocess.run(["git", "reset", "--hard"], check=True)
            else:
                print("\033[1;31m❌ Invalid choice. Please enter 'a' or 'b'.\033[0m")
        else:
            print("\033[1;31m❌ Source0 not found in the spec file.\033[0m")

    except FileNotFoundError:
        print("\033[1;31m❌ The specified spec file was not found.\033[0m")
    except subprocess.CalledProcessError as e:
        print(f"\033[1;31m❌ Command failed: {e}\033[0m")

if __name__ == "__main__":
    main()

