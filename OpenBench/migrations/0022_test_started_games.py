# Test.started_games: the games before Test.started, so that the ETA's speed counts only the games
# since then (tests that ran before 0020 had all their games counted at once). The start times so
# far are reset: set again at each test's next results.

from django.db import migrations, models

def forward(apps, schema_editor):
    apps.get_model('OpenBench', 'Test').objects.update(started=None)

class Migration(migrations.Migration):

    dependencies = [('OpenBench', '0021_machine_node_rate')]

    operations = [
        migrations.AddField('test', 'started_games', models.IntegerField(default=0)),
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
