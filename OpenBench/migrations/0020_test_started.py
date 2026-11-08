# Test.started: when the first results came (the test page's ETA). Tests from before: none.

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [('OpenBench', '0019_yugioh_ai_scale_nps')]

    operations = [migrations.AddField('test', 'started', models.DateTimeField(blank=True, null=True))]
