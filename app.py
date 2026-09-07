import sys
import itertools

def generate_wordlist(name, birth_year, keyword, output_file):
    print(f"[-] Building permutation matrix for target: {name}")
    
    base_words = {name, keyword, name.lower(), keyword.lower()}
    years = {birth_year, birth_year[-2:], ""}
    separators = {"", "_", ".", "-", "@"}
    numbers = {"", "123", "1234", "12345", "01", "777", "6767"}
    
    leet_map = {
        'a': ['a', '@', '4'],
        'e': ['e', '3'],
        'i': ['i', '1', '!'],
        'o': ['o', '0'],
        's': ['s', '$', '5'],
        't': ['t', '7']
    }

    def apply_leet(word):
        variants = [word]
        for char, replacements in leet_map.items():
            new_variants = []
            for v in variants:
                for r in replacements:
                    new_variants.append(v.replace(char, r))
            variants.extend(new_variants)
        return list(set(variants))

    wordlist = set()

    for w in base_words:
        # Apply leet transformations
        leeted = apply_leet(w)
        for l_word in leeted:
            # Basic combinations
            wordlist.add(l_word)
            
            for y in years:
                for sep in separators:
                    if y:
                        wordlist.add(f"{l_word}{sep}{y}")
                        wordlist.add(f"{y}{sep}{l_word}")
            
            for num in numbers:
                if num:
                    wordlist.add(f"{l_word}{num}")
                    wordlist.add(f"{num}{l_word}")

    # Write out to file
    with open(output_file, "w", encoding="utf-8") as f:
        for password in sorted(wordlist):
            f.write(password + "\n")
            
    print(f"[+] Wordlist compiled successfully. Total unique permutations: {len(wordlist)}")
    print(f"[+] Output saved to: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(f"Usage: python {sys.argv[0]} <name> <birth_year> <keyword> [output.txt]")
        sys.exit(1)
        
    target_name = sys.argv[1]
    target_year = sys.argv[2]
    target_keyword = sys.argv[3]
    outfile = sys.argv[4] if len(sys.argv) > 4 else "target_wordlist.txt"
    
    generate_wordlist(target_name, target_year, target_keyword, outfile)
