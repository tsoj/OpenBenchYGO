# Machine.node_rate and Machine.workload_started: the workers' throughput (the index's "Idle in").

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [('OpenBench', '0020_test_started')]

    operations = [
        migrations.AddField('machine', 'node_rate', models.FloatField(default=0.0)),
        migrations.AddField('machine', 'workload_started', models.DateTimeField(blank=True, null=True)),
    ]
