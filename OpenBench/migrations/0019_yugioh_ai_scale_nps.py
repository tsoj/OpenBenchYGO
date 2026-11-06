# The yugioh_AI engine's Scale NPS (the default of new tests): 10000, about the bots' bench speed
# on a 30-thread machine with all threads busy (it was a placeholder, 20000). Only clock time
# controls (BASE+INC) use it: those are scaled by it over the machine's bench speed.

from django.db import migrations

SCALE_NPS = 10000

def forward(apps, schema_editor):
    apps.get_model('OpenBench', 'EngineConfig').objects.filter(name='yugioh_AI').update(nps=SCALE_NPS)

class Migration(migrations.Migration):

    dependencies = [('OpenBench', '0018_nps_adjusted_nodes')]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
