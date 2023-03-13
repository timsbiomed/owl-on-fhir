"""Convert favorite code systems"""
import os
from argparse import ArgumentParser
from collections import OrderedDict
from typing import Dict

from owl_on_fhir.__main__ import PROJECT_DIR, owl_to_fhir


# Vars
DESCRIPTION = \
    'If present, will run all favorite ontologies found in pre-baked config variable `FAVORITE_ONTOLOGIES` in ' \
    '`owl_on_fhir/__main__.py`. . If using `--favorites`, the other CLI flags are not relevant. Instead, you '\
    'can customize by editing `FAVORITE_DEFAULTS` in `owl_on_fhir/__main__.py` if you are running a clone of '\
    'the project. Presently, the configure these favorites is not possible if running the installation from pip / PyPi.'
# - Vars: Config
# TODO: owl-on-fhir-content needs some configuration / setup instructions, or a git submodule
OWL_ON_FHIR_CONTENT_REPO_PATH = os.path.join(PROJECT_DIR, '..', 'owl-on-fhir-content')
# todo: consider 1+ changes: (i) external config JSON / env vars, (ii) accept overrides from CLI
FAVORITE_DEFAULTS = {
    'out_dir': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'output'),
    'intermediary_outdir': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input'),
    'include_all_predicates': True,
    'intermediary_type': 'obographs',
    'use_cached_intermediaries': True,
    'retain_intermediaries': True,
    'convert_intermediaries_only': False,
}
FAVORITE_ONTOLOGIES = OrderedDict({
    'mondo': {
        'download_url': 'https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.owl',
        'code_system_url': 'http://purl.obolibrary.org/obo/mondo.owl',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'mondo.owl'),
        'code_system_id': 'mondo',
        'native_uri_stems': ['http://purl.obolibrary.org/obo/MONDO_'],
    },
    'comp-loinc': {
        'download_url': 'https://github.com/loinc/comp-loinc/releases/latest/download/merged_reasoned_loinc.owl',
        'code_system_url': 'https://github.com/loinc/comp-loinc/releases/latest/download/merged_reasoned_loinc.owl',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'comploinc.owl'),
        'code_system_id': 'comp-loinc',
        'native_uri_stems': ['https://loinc.org/'],
    },
    'HPO': {
        'download_url': 'https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp-full.owl',
        'code_system_url': 'http://purl.obolibrary.org/obo/hp.owl',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'hpo.owl'),
        'code_system_id': 'HPO',
        'native_uri_stems': ['http://purl.obolibrary.org/obo/HP_'],
    },
    'rxnorm': {
        'download_url': 'https://data.bioontology.org/'
                        'ontologies/RXNORM/submissions/23/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb',
        'code_system_url': 'http://purl.bioontology.org/ontology/RXNORM',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'RXNORM.ttl'),
        'code_system_id': 'rxnorm',
        'native_uri_stems': ['http://purl.bioontology.org/ontology/RXNORM/'],
    },
    'sequence-ontology': {
        'download_url': 'https://data.bioontology.org/'
                        'ontologies/SO/submissions/304/download?apikey=8b5b7825-538d-40e0-9e9e-5ab9274a9aeb',
        'code_system_url': 'http://purl.bioontology.org/ontology/SO',
        'input_path': os.path.join(OWL_ON_FHIR_CONTENT_REPO_PATH, 'input', 'so.owl'),
        'code_system_id': 'sequence-ontology',
        'native_uri_stems': ['http://purl.obolibrary.org/obo/SO_'],
    },
})


def _run_favorites(
    use_cached_intermediaries: bool = None, retain_intermediaries: bool = None, include_all_predicates: bool = None,
    intermediary_type: str = None, out_dir: str = None, intermediary_outdir: str = None,
    convert_intermediaries_only: bool = None, dev_oak_path: str = None, dev_oak_interpreter_path: str = None,
    favorites: Dict = FAVORITE_ONTOLOGIES
):
    """Convert favorite ontologies"""
    kwargs = {k: v for k, v in locals().items() if v is not None and not k.startswith('__') and k != 'favorites'}
    fails = []
    successes = []
    n = len(favorites)
    i = 0
    for d in favorites.values():
        i += 1
        print('Converting {} of {}: {}'.format(i, n, d['code_system_id']))
        try:
            owl_to_fhir(
                out_filename=f'CodeSystem-{d["code_system_id"]}.json',
                input_path_or_url=d['input_path'] if d['input_path'] else d['download_url'], **kwargs)
            successes.append(d['id'])
        except Exception as e:
            fails.append(d['code_system_id'])
            print('Failed to convert {}: \n{}'.format(d['code_system_id'], e))
    print('SUMMARY')
    print('Successes: ' + str(successes))
    print('Failures: ' + str(fails))


def favs_cli():
    """Command line interface."""
    parser = ArgumentParser(prog='OWL on FHIR: Favorites', description=DESCRIPTION)
    parser.add_argument(
        '-d', '--dev-oak-path', default=False, required=False,
        help='If you want to use a local development version of OAK, specify the path to the OAK directory here. '
             'Must be used with --dev-oak-interpreter-path.')
    parser.add_argument(
        '-D', '--dev-oak-interpreter-path', default=False, required=False,
        help='If you want to use a local development version of OAK, specify the path to the Python interpreter where '
             'its dependencies are installed (i.e. its virtual environment). Must be used with --dev-oak-path.')

    d: Dict = vars(parser.parse_args())
    _run_favorites(
        dev_oak_path=d['dev_oak_path'], dev_oak_interpreter_path=d['dev_oak_interpreter_path'],
        **{**FAVORITE_DEFAULTS, **{'favorites': FAVORITE_ONTOLOGIES}})


# Execution
if __name__ == '__main__':
    favs_cli()
