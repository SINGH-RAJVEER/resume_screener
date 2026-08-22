"""Build the skill vocabulary corpus from public O*NET data plus curated entries.

Sources (download manually, license CC BY 4.0):
	O*NET Database (text edition): https://www.onetcenter.org/database.html
		- Technology Skills.txt  -> technology skills with commodity categories
		- Skills.txt             -> canonical cross-domain skills
		- Knowledge.txt          -> canonical knowledge areas
	Optional ESCO titles JSON produced by scripts/fetch_esco_titles.py.

Writes worker/documents/skills_corpus.json. Deterministic: same inputs,
same output bytes.
"""

import csv
import json
import sys
from pathlib import Path

# Curated entries fill gaps in O*NET: standalone languages/initialisms and
# general competencies that resumes commonly name.
CURATED = [
	("SQL", "Database query languages", ["t-sql", "pl/sql"]),
	("AWS", "Cloud platforms", ["amazon web services"]),
	("Azure", "Cloud platforms", ["microsoft azure"]),
	("Google Cloud Platform", "Cloud platforms", ["gcp", "google cloud"]),
	("Machine Learning", "Data science", ["ml"]),
	("Deep Learning", "Data science", []),
	("Artificial Intelligence", "Data science", ["ai"]),
	# Modern tools absent from O*NET 30.0.
	("Snowflake", "Data warehousing", ["snowflake db"]),
	("dbt", "Data engineering", []),
	("PostgreSQL", None, ["postgres"]),
	("Kubernetes", None, ["k8s"]),
	("JavaScript", None, ["js"]),
	("TypeScript", None, ["ts"]),
	("Python", None, ["py"]),
	# O*NET stores some tools under vendor-prefixed names; resumes rarely do.
	("Apache Kafka", None, ["kafka"]),
	("IBM Terraform", None, ["terraform"]),
	("Apache Airflow", None, ["airflow"]),
	("Communication", "General competencies", ["communication skills"]),
	("Teamwork", "General competencies", ["team collaboration"]),
	("Leadership", "General competencies", ["people management"]),
	("Problem Solving", "General competencies", ["problem-solving"]),
	("Public Speaking", "General competencies", []),
]

MIN_NAME_LENGTH = 2
MAX_PHRASE_TOKENS = 6

# Phrases that consume tokens during matching but are not skills: they absorb
# education and credential mentions before shorter cross-domain elements
# (e.g. Science) match inside them.
ABSORBERS = ["Computer Science"]


def read_onet_tech_skills(path: Path) -> list[tuple[str, str]]:
	with path.open(newline="") as handle:
		return [
			(row["Example"], row["Commodity Title"])
			for row in csv.DictReader(handle, delimiter="\t")
		]


def read_onet_element_names(paths: list[Path]) -> list[str]:
	names: set[str] = set()
	for path in paths:
		with path.open(newline="") as handle:
			names.update(row["Element Name"] for row in csv.DictReader(handle, delimiter="\t"))
	return sorted(names)


def build(onet_dir: Path, esco_path: Path | None) -> dict:
	skills: dict[str, dict] = {}

	def add(name: str, category: str | None) -> None:
		name = " ".join(name.split())
		if len(name) < MIN_NAME_LENGTH or len(name.split()) > MAX_PHRASE_TOKENS:
			return
		key = name.casefold()
		skills.setdefault(key, {"name": name, "category": category})

	for example, commodity in read_onet_tech_skills(onet_dir / "Technology Skills.txt"):
		add(example, commodity)
	for element in read_onet_element_names([onet_dir / "Skills.txt", onet_dir / "Knowledge.txt"]):
		add(element, "Cross-domain skills")
	if esco_path is not None and esco_path.exists():
		for title in json.loads(esco_path.read_text()):
			add(title, "ESCO")
	for name, category, _ in CURATED:
		add(name, category)

	aliases: dict[str, str] = {}
	for name, _, alias_list in CURATED:
		for alias in [name.casefold(), *(a.casefold() for a in alias_list)]:
			existing = aliases.setdefault(alias, name)
			if existing != name:
				raise ValueError(f"Alias collision for {alias!r}: {existing} vs {name}")
	for key, entry in sorted(skills.items()):
		previous = aliases.setdefault(key, entry["name"])
		if previous != entry["name"]:
			raise ValueError(f"Alias collision for {key!r}: {previous} vs {entry['name']}")

	return {
		"version": sys.argv[2] if len(sys.argv) > 2 else "dev",
		"sources": [
			"O*NET 30.0 Technology Skills, Skills, Knowledge (CC BY 4.0)",
			"curated aliases",
			*(
				["ESCO v1.2 preferred labels"]
				if esco_path is not None and esco_path.exists()
				else []
			),
		],
		"skills": [skills[key] for key in sorted(skills)],
		"aliases": {alias: aliases[alias] for alias in sorted(aliases)},
		"absorbers": [absorber.casefold() for absorber in ABSORBERS],
	}


USAGE = "usage: build_skills_corpus.py ONET_TEXT_DIR OUTPUT_JSON [ESCO_TITLES_JSON]"


def main() -> None:
	if len(sys.argv) < 3:
		raise SystemExit(USAGE)
	onet_dir = Path(sys.argv[1])
	output = Path(sys.argv[2])
	esco_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
	corpus = build(onet_dir, esco_path)
	output.write_text(json.dumps(corpus, ensure_ascii=False, sort_keys=True))
	print(f"wrote {len(corpus['skills'])} skills, {len(corpus['aliases'])} aliases to {output}")


if __name__ == "__main__":
	main()
