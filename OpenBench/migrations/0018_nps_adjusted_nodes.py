# The time control NPS=X is now dev NpsAdjustedN=X with base N=X (base X nodes per decision, dev X
# times its nodes/s ratio to base): the tests and the engines' presets. Tunes play one engine
# against itself: N=X.

import re

from django.db import migrations

NPS = re.compile(r'NPS=(\d+)$')

def preset_controls(preset, adjusted):
    if not (match := NPS.match(preset.get('both_time_control', ''))):
        return
    del preset['both_time_control']
    nodes = match.group(1)
    if adjusted:
        preset['dev_time_control' ] = 'NpsAdjustedN=%s' % (nodes)
        preset['base_time_control'] = 'N=%s' % (nodes)
    else:
        preset['both_time_control'] = 'N=%s' % (nodes)

def forward(apps, schema_editor):

    for test in apps.get_model('OpenBench', 'Test').objects.filter(dev_time_control__startswith='NPS='):
        nodes = NPS.match(test.dev_time_control).group(1)
        test.dev_time_control  = 'NpsAdjustedN=%s' % (nodes)
        test.base_time_control = 'N=%s' % (nodes)
        test.save(update_fields=['dev_time_control', 'base_time_control'])

    for config in apps.get_model('OpenBench', 'EngineConfig').objects.all():
        for kind, adjusted in (('test_presets', True), ('datagen_presets', True), ('tune_presets', False)):
            for preset in config.presets.get(kind, {}).values():
                preset_controls(preset, adjusted)
        config.save(update_fields=['presets'])

class Migration(migrations.Migration):

    dependencies = [('OpenBench', '0017_network_ob_compressed')]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
