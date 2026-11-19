import sys
from pathlib import Path


def countFiles(companiesDir: Path) -> dict:
	pyCount = 0
	otherCount = 0
	allFiles = companiesDir.rglob("*")
	for filePath in allFiles:
		isFile = filePath.is_file()
		if isFile:
			isPycache = "__pycache__" in filePath.parts
			if isPycache:
				continue
			isPyFile = filePath.suffix == ".py"
			if isPyFile:
				pyCount = pyCount + 1
			else:
				otherCount = otherCount + 1
	counts = {"py": pyCount, "other": otherCount}
	return counts


def main() -> None:
	hasArg = len(sys.argv) > 1
	if hasArg:
		companiesDirArg = sys.argv[1]
	else:
		companiesDirArg = "companies"
	companiesDir = Path(companiesDirArg)
	dirExists = companiesDir.exists()
	if not dirExists:
		print(f"Directory not found: {companiesDir}")
		return
	counts = countFiles(companiesDir)
	pyCount = counts["py"]
	otherCount = counts["other"]
	totalCount = pyCount + otherCount
	print(f"Companies directory: {companiesDir}")
	print(f".py files:     {pyCount}")
	print(f"non-.py files: {otherCount}")
	print(f"total files:   {totalCount}")


if __name__ == "__main__":
	main()