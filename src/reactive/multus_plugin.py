import os
import shutil
import tarfile
from pathlib import Path
from subprocess import check_output

from charms.reactive import when, when_not, set_flag
from charms.reactive import endpoint_from_flag

from charmhelpers.core import unitdata
from charmhelpers.core.hookenv import network_get, log, config, resource_get

from charms.layer import status


MULTUS_TMP_DIR = Path('/tmp/multus')
MULTUS_DAEMONSET = MULTUS_TMP_DIR / 'images' / 'multus-daemonset.yml'
FLANNEL_DAEMONSET = MULTUS_TMP_DIR / 'images' / 'flannel-daemonset.yml'

kv = unitdata.kv()


kubeclientconfig_path = '/root/.kube/config'


def kubectl(*args):
    ''' Run a kubectl cli command with a config file. Returns stdout and throws
    an error if the command fails. '''
    command = \
        ['/snap/bin/kubectl', '--kubeconfig=' + kubeclientconfig_path] + \
        list(args)
    log('Executing {}'.format(command))
    return check_output(command)


@when_not('cni.interface.cidr.acquired')
def get_bind_interface_cidr():
    '''Acquire non-fan interface, cidr for the cni endpoint '''
    try:
        data = network_get('cni')
    except NotImplementedError:
        # Juju < 2.1
        status.blocked('Need Juju > 2.3')
        return

    if 'bind-addresses' not in data:
        # Juju < 2.3
        status.blocked('Need Juju > 2.3')
        return

    for bind_address in data['bind-addresses']:
        if bind_address['interfacename'].startswith('fan-'):
            continue
        if bind_address['interfacename'] and \
           bind_address['addresses'][0]['cidr']:
            kv.set('interfacename', bind_address['interfacename'])
            kv.set('cidr', config('cidr'))
            set_flag('cni.interface.cidr.acquired')
            return

    status.blocked('Unable to create CNI configuration.')
    return


@when('cni.is-master',
      'cni.interface.cidr.acquired')
@when_not('multus.cni.configured')
def configure_master_cni():
    status.maint('Configuring Multus CNI')
    cni = endpoint_from_flag('cni.is-master')

    # If multus directory doesnt exist create irt
    if not MULTUS_TMP_DIR.exists():
        MULTUS_TMP_DIR.mkdir()

    # Remove anything that could possibly pre-exist
    shutil.rmtree(str(MULTUS_TMP_DIR / "*"), ignore_errors=True)

    
    # Acquire and provision the multus resource
    #multus = resource_get('multus')
    #if os.stat(multus).st_size > 0:
    #    tar = tarfile.open(multus)
    #    tar.extractall(path=str(MULTUS_TMP_DIR))
    #    tar.close()
    #    log("Multus Installed")

    #for daemonset in [MULTUS_DAEMONSET, FLANNEL_DAEMONSET]:
    #    kubectl('apply', '-f', str(daemonset))

    cni.set_config(cidr=kv.get('cidr'))
    set_flag('multus.cni.configured')


@when('cni.is-worker',
      'cni.interface.cidr.acquired')
@when_not('multus.cni.configured')
def configure_worker_cni():
    ''' Configure Multus CNI. '''
    status.maint('Configuring Multus CNI')
    cni = endpoint_from_flag('cni.is-worker')
    cni.set_config(cidr=kv.get('cidr'))
    set_flag('multus.cni.configured')


@when('multus.cni.configured')
def set_cni_configured_status():
    status.active('Multus cni configured')
