"""
Very simple CLI to generate a single JSON mapping of image name -> importer code from 
the importer repo yaml files.
"""

from pathlib import Path
import sys
import yaml
import json


def main():
    # TODO CODE use argparse if things get complicated
    # TODO CODE add means of skipping bad yamls for testing purposes
    importer_repo_dir = sys.argv[1]
    output_file = sys.argv[2]
    dir_path = Path(importer_repo_dir).resolve() / "cdmeventimporters"
    print(f"Loading yaml files from {dir_path}")
    yamls = [
        p.resolve() for p in dir_path.iterdir()
        if p.suffix in {'.yaml', '.yml'} and p.is_file()
    ]
    data = {}
    for yamfile in yamls:
        print(f"Processing yaml file {yamfile}")
        with open(yamfile) as y:
            contents = yaml.safe_load(y)
        image = contents.get("image")
        mod = contents.get("py_module")
        meta = contents.get("importer_meta")
        if not image or not mod:
            raise ValueError(
                f"YAML file at {yamfile} does not have required fields. Contents:\n{contents}"
            )
        if image in data:
            raise ValueError(
                f"YAML file conflict for image {image}: {yamfile}, {data['image']['file']}"
            )
        data[image] = {"mod": mod, "file": str(yamfile), "meta": meta if meta else {}}
    with open(output_file, "w") as o:
        o.write(json.dumps(data, indent=4))


if __name__ == "__main__":
    main()
