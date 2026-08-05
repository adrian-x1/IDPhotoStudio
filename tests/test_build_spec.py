from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_build_inputs() -> dict:
    spec_path = PROJECT_ROOT / "build.spec"
    source = spec_path.read_text(encoding="utf-8")
    prefix, separator, _ = source.partition("\na = Analysis(")
    if not separator:
        raise AssertionError("Analysis marker not found in build.spec")
    namespace: dict = {}
    exec(compile(prefix, str(spec_path), "exec"), namespace)
    return namespace


class BuildSpecTests(unittest.TestCase):
    def test_pymatting_distribution_metadata_is_bundled(self) -> None:
        datas = load_build_inputs()["datas"]
        metadata_entries = [
            (Path(source), Path(destination))
            for source, destination in datas
            if Path(destination).name.startswith("pymatting-")
            and Path(destination).name.endswith(".dist-info")
        ]

        self.assertEqual(len(metadata_entries), 1)
        metadata_source, _ = metadata_entries[0]
        self.assertTrue((metadata_source / "METADATA").is_file())


if __name__ == "__main__":
    unittest.main()
