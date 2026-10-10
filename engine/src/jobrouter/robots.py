"""Robots policy matching with longest-path and most-specific-agent precedence."""
import re
from urllib.parse import urlsplit


class RobotsPolicy:
    def __init__(self, text, user_agent):
        groups = []
        agents, rules = [], []
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if rules:
                    groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(value.lower())
            elif agents and key in ("allow", "disallow", "crawl-delay"):
                rules.append((key, value))
        if agents:
            groups.append((agents, rules))
        ua = user_agent.lower()
        match_lengths = [max([len(a) for a in ag if a != "*" and a in ua] or [0]) for ag, _ in groups]
        strongest = max(match_lengths or [0])
        selected = [rules for (agents, rules), length in zip(groups, match_lengths)
                    if (length == strongest if strongest else "*" in agents)]
        self.rules = [rule for group in selected for rule in group]
        delays = []
        for key, value in self.rules:
            if key == "crawl-delay":
                try:
                    delay = float(value)
                    if 0 <= delay <= 3600:
                        delays.append(delay)
                except ValueError:
                    pass
        self.delay = max(delays or [0])

    def allows(self, url):
        p = urlsplit(url)
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        matches = []
        for key, rule in self.rules:
            if key not in ("allow", "disallow") or not rule:
                continue
            anchored = rule.endswith("$")
            body = rule[:-1] if anchored else rule
            regex = "^" + re.escape(body).replace(r"\*", ".*") + ("$" if anchored else "")
            if re.search(regex, path):
                matches.append((len(body.replace("*", "").encode()), key == "allow"))
        return max(matches)[1] if matches else True
