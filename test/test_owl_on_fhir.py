"""Tests

Can run all tests in all files by running this from root of TermHub:
    python -m unittest discover
"""
import os
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
TEST_INPUT_DIR = TEST_DIR / 'input'
TEST_OUTPUT_DIR = TEST_DIR / 'output'
PROJECT_ROOT = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
from owl_on_fhir.__main__ import owl_to_fhir


# class Omop2Fhir:
class TestOmop2Fhir(unittest.TestCase):
    """Tests"""

    def test_defaults(self):
        """Test default settings, except for including all relationships"""
        # Vars
        out_dir = TEST_OUTPUT_DIR / 'test_defaults'
        settings = {
            # input_path_or_url  # handled below
            # code_system_id: str = None,  # handled below
            'out_dir': out_dir,
            'retain_intermediaries': True,  # todo: temporary for troubleshooting
            # using defaults:
            # out_filename: str = None,
            # include_only_critical_predicates = False,

            # use_cached_intermediaries = False,
            # intermediary_outdir: str = None,
            # convert_intermediaries_only = False,
            # native_uri_stems: List[str] = None,
            # code_system_url: str = None,
            # dev_oak_path: str = None,
            # dev_oak_interpreter_path: str = None,
            # rxnorm_bioportal = False
        }
        # Run program
        for file in os.listdir(out_dir):
            path = out_dir / file
            if not os.path.isdir(path):
                os.remove(path)

        # Case 1: RxNorm
        print('test_defaults: OMOP-RxNorm')
        owl_to_fhir(TEST_INPUT_DIR / 'OMOP-RxNorm.owl', code_system_id='OMOP-RxNorm', **settings)
        # TODO: CodeSystem & ConceptMap
        # todo: read JSON and check
        # ids = []
        # rels = []
        # rel_set = set([x[1] for x in rels])
        # self.assertGreater(len(ids), 100)
        # self.assertGreater(len(rels), 50)
        # self.assertIn('rdfs:subClassOf', rel_set)

        # Case 2: OMOP (several ontologies/vocabs combined; not actually all of OMOP)
        print('test_defaults: OMOP')
        owl_to_fhir(TEST_INPUT_DIR / 'OMOP.owl', code_system_id='OMOP', **settings)
        print()


# todo: print: for some reason stuff is not printing. When I run tests in another project, they do print. Supposedly
#  it is not uncommon (default?) for things not to print though. id liek to fix if i can, so I can see progress
# TODO: add back unittest superclass
# Special debugging: To debug in PyCharm and have it stop at point of error, change TestOmop2Owl(unittest.TestCase)
#  to TestOmop2Fhir, and uncomment below.
if __name__ == '__main__':
    tester = TestOmop2Fhir()
    # tester = Omop2Fhir()
    tester.test_defaults()
