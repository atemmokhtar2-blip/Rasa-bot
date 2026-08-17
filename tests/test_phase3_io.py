from framework.datasets.io import CSVImporter, FrameworkJSONExporter, JSONImporter, JSONLImporter, RasaExporter
from framework.datasets.system import DatasetVersion, TrainingExample

def dataset(): return DatasetVersion('d1', 'v1', 'p1', (TrainingExample('hello', 'greet', language='en'), TrainingExample('حالة الطلب', 'get_order_status')))

def test_json_jsonl_csv_importers():
    assert len(JSONImporter().import_data('[{"text":"hello","intent":"greet"}]', project_id='p', dataset_id='d', version='v').examples) == 1
    assert len(JSONLImporter().import_data('{"text":"hello","intent":"greet"}\n', project_id='p', dataset_id='d', version='v').examples) == 1
    assert CSVImporter().import_data('text,intent\nhello,greet\n', project_id='p', dataset_id='d', version='v').examples[0].intent == 'greet'

def test_framework_and_rasa_exporters():
    framework = FrameworkJSONExporter().export(dataset()); rasa = RasaExporter().export(dataset())
    assert framework['checksum'] and 'examples' in framework
    assert rasa['nlu.yml']['version'] == '3.1' and rasa['domain.yml']['intents'] == ['get_order_status', 'greet']
