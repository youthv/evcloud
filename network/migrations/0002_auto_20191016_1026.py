# Generated by Django 2.2.6 on 2019-10-16 02:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('network', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='vlan',
            name='dhcp_config',
            field=models.TextField(default='', verbose_name='DHCP部分配置信息'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='vlan',
            name='dns_server',
            field=models.GenericIPAddressField(verbose_name='DNS服务IP'),
        ),
        migrations.AlterField(
            model_name='vlan',
            name='gateway',
            field=models.GenericIPAddressField(verbose_name='网关'),
        ),
        migrations.AlterField(
            model_name='vlan',
            name='net_mask',
            field=models.GenericIPAddressField(verbose_name='子网掩码'),
        ),
    ]