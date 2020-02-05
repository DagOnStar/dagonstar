import os
import time

from enum import Enum
from libcloud.compute.providers import get_driver
from libcloud.compute.types import NodeState
from libcloud.compute.types import Provider

from dagon.config import read_config


class CloudManager(object):
    """
    Manages the connection with the cloud providers using LibCloud
    """

    @staticmethod
    def get_instance(keyparams, provider, name=None, flavour=None, instance_id=None):
        """
        Get or create an instance in the specified cloud provider

        :param keyparams: dictionary with the ssh key
        :type keyparams: dict(str, str)

        :param provider: cloud provider
        :type provider: :class:`libcloud.compute.types.Provider`

        :param name: instance name (for existing instances)
        :type name: str

        :param flavour: dictionary with the instance configuration (size, region, operating system)
        :type flavour: dict

        :param instance_id: instance id in the cloud provider (for existing instances)
        :type instance_id: str

        :return: instance created
        :rtype: :class:`libcloud.compute.base.Node`
        """

        driver = get_driver(provider)
        conf = read_config(section=str(provider))
        if provider == Provider.GCE:
            conn = driver(conf['key'], conf['secret'], project=conf['project'])
        else:
            conn = driver(**conf)
        manager = globals()[str(provider).upper()]
        node = manager.create_instance(conn, name, flavour, keyparams) if flavour is not None \
            else CloudManager.get_existing_instance(conn, id=instance_id, name=name)
        node = CloudManager.wait_until_running(conn, node)
        return node

    @staticmethod
    def wait_until_running(conn, node):
        """
        wait until an instance is running

        :param conn: driver to the cloud provider
        :type conn: Libcloud driver

        :param node: node to waite
        :type node: :class:`libcloud.compute.base.Node`

        :return: instance updated
        :rtype node: :class:`libcloud.compute.base.Node`
        """

        while node.state is not NodeState.RUNNING:
            try:
                node = CloudManager.get_existing_instance(conn, uuid=node.uuid)
            except Exception:
                pass
            time.sleep(1)
        return node

    @staticmethod
    def create_instance(conn, name, flavour, keyparams):
        """
        create a new instance on the cloud provider

        :param conn: driver to the cloud provider
        :type conn: Libcloud driver

        :param name: instance name
        :param name: str

        :param flavour: dictionary with the instance configuration (size, region, operating system)
        :type flavour: dict

        :param keyparams: dictionary with the ssh key
        :type keyparams: dict(str, str)

        :return: instance created
        :rtype node: :class:`libcloud.compute.base.Node`
        """

        if flavour is None:
            raise Exception('The characteristics of the image has not been specified')

        sizes = conn.list_sizes()
        size = [s for s in sizes if s.id == flavour['size']]
        image = conn.get_image(flavour['image'])
        size = size[0] if len(size) > 0 else None
        key = None

        if image is None or size is None:
            raise Exception('Size or image doesn\'t exists')

        if keyparams['option'] == KeyOptions.CREATE:
            key = KeyPair.createPairKey(conn, keyparams['keypath'], keyparams['cloudargs'])
        elif keyparams['option'] == KeyOptions.GET:
            key = KeyPair.getExistingPairKey(conn, keyparams['keyname'])
        elif keyparams['option'] == KeyOptions.IMPORT:
            key = KeyPair.importKey(conn, keyparams['keypath'])

        node = conn.create_node(name=name, image=image, size=size,
                                ex_keyname=key.name)
        return node

    @staticmethod
    def get_existing_instance(conn, id=None, name=None, uuid=None):
        """
        return an existing instance from the cloud provider. The id, name or uuid is used to get the instance.


        :param conn: driver to the cloud provider
        :type conn: Libcloud driver

        :param id: instance id
        :type id: str

        :param name: instance name
        :type name: str

        :param uuid: instance uuid
        :type uuid: str

        :return: instance
        :rtype node: :class:`libcloud.compute.base.Node`
        """
        if id is None and name is None and uuid is None:
            raise Exception('Must specified an intance\'s id or name')
        nodes = conn.list_nodes()
        node = None
        if id is not None:
            node = [node for node in nodes if node.id == id]
        elif name is not None:
            node = [node for node in nodes if node.name == name]
        elif uuid is not None:
            node = [node for node in nodes if node.uuid == uuid]
        if len(node) == 0:
            raise Exception('Instance doesn\'t exists')
        return node[0]


class KeyOptions(Enum):
    """
    Represents the different options to manage the keys instance. The key could be create from the scratch,
    import an existing local key or get an existing key on the cloud provider

    :cvar CREATE: create a new key
    :cvar IMPORT: import a key
    :cvar GET: get an existing key
    """

    CREATE = "CREATE"
    IMPORT = "IMPORT"
    GET = "GET"


class KeyPair(object):

    @staticmethod
    def generate_RSA(bits=2048):
        """
        Generate an RSA keypair with an exponent of 65537 in PEM format

        :param bits: bits The key length in bits
        :type bits: int

        :return: Return private key and public key
        """

        from Crypto.PublicKey import RSA
        new_key = RSA.generate(bits, e=65537)
        public_key = new_key.publickey().exportKey("OpenSSH")
        private_key = new_key.exportKey("PEM")
        return private_key, public_key

    @staticmethod
    def writeKey(privateKey, filename):
        """
        writes the private key in a file

        :param privateKey: key string
        :type privateKey: str

        :param filename: path to the file where the key will be saved
        :type filename: str
        """

        from os import chmod
        with open(filename, 'w') as content_file:
            chmod(filename, 0o600)
            content_file.write(privateKey)

    @staticmethod
    def createPairKey(conn, filename, args):
        """
        create a new key on the cloud provider

        :param conn: driver to the cloud provider
        :type conn: Libcloud driver

        :param filename: path to the file where the key will be saved
        :type filename: str

        :param args: arguments to create the key
        :type args: dict()

        :return: key pair object
        """

        from inspect import getargspec

        # CHECK FOR THE PARAMS OF THE FUNCTION
        sig = getargspec(conn.create_key_pair)
        foo_args = sig.args
        foo_params = dict()

        for arg in foo_args:
            if arg in args:
                foo_params[arg] = args[arg]

        # CREATE NEW KEY
        key_pair = conn.create_key_pair(**foo_params)
        private_key = key_pair.private_key
        if private_key is None:
            private_key = args['private_key']
        KeyPair.writeKey(private_key, filename)
        return key_pair

    @staticmethod
    def getExistingPairKey(conn, keyname):
        """
        returns an existing pair key from the cloud provider

        :param conn: driver to the cloud provider
        :type conn: Libcloud driver

        :param keyname: name of the key on the cloud provider
        :type keyname: str

        :return: key pair object
        """
        keys = conn.list_key_pairs()
        key_pair = [key for key in keys if key.name == keyname]
        key_pair = key_pair[0] if len(key_pair) > 0 else None
        return key_pair

    @staticmethod
    def importKey(conn, key_path):
        """
        import an existing key from a local file

        :param conn: driver to the cloud provider
        :type conn: Libcloud driver

        :param key_path: path to the key
        :param key_path: str

        :return: key pair object
        """

        key_file_path = os.path.expanduser(key_path)
        key_pair = conn.import_key_pair_from_file(name=key_path,
                                                  key_file_path=key_file_path)
        return key_pair


class EC2(object):
    """
    Manages the creation of instances on Amazon EC2 using libcloud
    """

    @staticmethod
    def createInstance(conn, name, flavour, keyparams):
        """
        create a new instance on amazon EC2

        :param conn: driver to the cloud provider
        :type conn: EC2 Libcloud driver

        :param name: instance name
        :param name: str

        :param flavour: dictionary with the instance configuration (size, region, operating system)
        :type flavour: dict

        :param keyparams: dictionary with the ssh key
        :type keyparams: dict(str, str)

        :return: instance created
        :rtype node: :class:`libcloud.compute.base.Node`
        """

        if flavour is None:
            raise Exception('The characteristics of the image has not been specified')

        sizes = conn.list_sizes()
        size = [s for s in sizes if s.id == flavour['size']]
        image = conn.get_image(flavour['image'])
        size = size[0] if len(size) > 0 else None
        key = None

        if image is None or size is None:
            raise Exception('Size or image doesn\'t exists')
        if keyparams['option'] == KeyOptions.CREATE:
            key = KeyPair.createPairKey(conn, keyparams['key_path'], keyparams['cloud_args'])
        elif keyparams['option'] == KeyOptions.GET:
            key = KeyPair.getExistingPairKey(conn, keyparams['cloud_args']['name'])
        elif keyparams['option'] == KeyOptions.IMPORT:
            key = KeyPair.importKey(conn, keyparams['key_path'])

        node = conn.create_node(name=name, image=image, size=size,
                                ex_keyname=key.name)
        return node


class DIGITALOCEAN(object):
    """
    Manages the creation of instances on DigitalOcean using libcloud
    """

    @staticmethod
    def createInstance(conn, name, flavour, keyparams):
        """
        create a new instance on DigitalOcean

        :param conn: driver to the cloud provider
        :type conn: DigitalOcean Libcloud driver

        :param name: instance name
        :param name: str

        :param flavour: dictionary with the instance configuration (size, region, operating system)
        :type flavour: dict

        :param keyparams: dictionary with the ssh key
        :type keyparams: dict(str, str)

        :return: instance created
        :rtype node: :class:`libcloud.compute.base.Node`
        """

        if flavour is None:
            raise Exception('The characteristics of the image has not been specified')

        sizes = conn.list_sizes()
        size = [s for s in sizes if s.id == flavour['size']]
        image = conn.get_image(flavour['image'])
        size = size[0] if len(size) > 0 else None
        locations = conn.list_locations()
        location = [l for l in locations if l.id == flavour['location']]
        location = location[0] if len(location) > 0 else None
        key = None

        if image is None or size is None or location is None:
            raise Exception('Size, location or image doesn\'t exists')
        if keyparams['option'] == KeyOptions.CREATE:
            key = KeyPair.createPairKey(conn, keyparams['key_path'], keyparams['cloudargs'])
        elif keyparams['option'] == KeyOptions.GET:
            key = KeyPair.getExistingPairKey(conn, keyparams['keyname'])
        elif keyparams['option'] == KeyOptions.IMPORT:
            key = KeyPair.importKey(conn, keyparams['keypath'])

        node = conn.create_node(name=name, image=image, size=size, location=location,
                                ex_create_attr={"ssh_keys": [key.fingerprint]})
        return node


class GCE(object):
    """
    Manages the creation of instances on google cloud using libcloud
    """

    @staticmethod
    def createInstance(conn, name, flavour, keyparams):
        """
        create a new instance on google cloud

        :param conn: driver to the cloud provider
        :type conn: google cloud Libcloud driver

        :param name: instance name
        :param name: str

        :param flavour: dictionary with the instance configuration (size, region, operating system)
        :type flavour: dict

        :param keyparams: dictionary with the ssh key
        :type keyparams: dict(str, str)

        :return: instance created
        :rtype node: :class:`libcloud.compute.base.Node`
        """

        if flavour is None:
            raise Exception('The characteristics of the image has not been specified')

        image = flavour['image']
        location = flavour['location']
        size = flavour['size']

        metadata = {"items": [
            {"value": "%s: %s %s" % (keyparams['username'], keyparams['public_key'], keyparams['username']),
             "key": "ssh-keys"}]}

        KeyPair.writeKey(keyparams["private_key"], keyparams['keypath'])
        node = conn.create_node(name=name, image=image, size=size, location=location, ex_metadata=metadata)

        return node
