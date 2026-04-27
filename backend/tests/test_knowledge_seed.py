from app.seed.knowledge_seed import load_dataset, validate_dataset


def test_core_v1_dataset_validation_passes():
    dataset = load_dataset("core_v1")
    validate_dataset(dataset)
