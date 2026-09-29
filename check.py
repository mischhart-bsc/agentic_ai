import config
p = config.ROOT / "prompts" / "step1_baseline.txt"
print(p.resolve(), p.stat().st_size)