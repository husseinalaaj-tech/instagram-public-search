import sys
import itertools

def generate_targeted_wordlist(output_file="target_wordlist.txt"):
    # Target Intelligence Seeds
    first_names = ["adian", "adyan"]
    last_names = ["alboherb", "alborebh"]
    dates = ["24", "02", "2006", "06", "2402", "24022006", "240206", "feb24", "24feb"]
    separators = ["", ".", "_", "-"]
    
    wordlist = set()
    
    # Base combinations (First + Last, Last + First, Emails)
    for f in first_names:
        for l in last_names:
            for sep in separators:
                wordlist.add(f"{f}{sep}{l}")
                wordlist.add(f"{l}{sep}{f}")
                wordlist.add(f"{f}{sep}{l[0]}")
                wordlist.add(f"{f[0]}{sep}{l}")
                
    # Add birthdate permutations
    base_bases = list(wordlist) + first_names + last_names + ["adian.alborebh", "adian_alborebh"]
    
    for base in base_bases:
        for d in dates:
            for sep in separators:
                wordlist.add(f"{base}{sep}{d}")
                wordlist.add(f"{d}{sep}{base}")

    # Capitalization variations (Title case, UPPER, lower)
    final_passwords = set()
    for pwd in wordlist:
        final_passwords.add(pwd.lower())
        final_passwords.add(pwd.capitalize())
        final_passwords.add(pwd.upper())
        # Capitalize both parts if separated
        for sep in ['.', '_', '-']:
            if sep in pwd:
                parts = pwd.split(sep)
                final_passwords.add(sep.join([p.capitalize() for p in parts]))

    # Write out to file
    with open(output_file, "w", encoding="utf-8") as f:
        for pwd in sorted(final_passwords):
            f.write(pwd + "\n")
            
    print(f"[+] Targeted intelligence wordlist compiled successfully.")
    print(f"[+] Total unique permutations generated: {len(final_passwords)}")
    print(f"[+] Output saved to: {output_file}")

if __name__ == "__main__":
    outfile = sys.argv[1] if len(sys.argv) > 1 else "adian_wordlist.txt"
    generate_targeted_wordlist(outfile)
