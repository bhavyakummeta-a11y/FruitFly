"""Explicit download of the public datasets used by the starter notebook."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

SOURCES = {
    'Completeness_783.csv': ('philshiu/Drosophila_brain_model', 'Completeness_783.csv'),
    'Connectivity_783.parquet': ('philshiu/Drosophila_brain_model', 'Connectivity_783.parquet'),
    'annotations.tsv': ('flyconnectome/flywire_annotations',
                        'supplemental_files/Supplemental_file1_neuron_annotations.tsv'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='data/brain')
    args = parser.parse_args()
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Resolve branches once, then download immutable commit URLs and record hashes.
    commits = {}
    manifest = {}
    for name, (repo, path) in SOURCES.items():
        if repo not in commits:
            with urllib.request.urlopen(f'https://api.github.com/repos/{repo}/commits/main', timeout=30) as r:
                commits[repo] = json.load(r)['sha']
        url = f'https://raw.githubusercontent.com/{repo}/{commits[repo]}/{path}'
        target = directory / name
        partial = directory / (name + '.partial')
        print(f'Downloading {name} ...', flush=True)
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=60) as source, partial.open('wb') as out:
                while chunk := source.read(1024 * 1024):
                    out.write(chunk)
                    digest.update(chunk)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        manifest[name] = {'url': url, 'sha256': digest.hexdigest(), 'bytes': target.stat().st_size}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Data and provenance saved to {directory}')


if __name__ == '__main__':
    main()
