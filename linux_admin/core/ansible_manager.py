import os
import tempfile
import subprocess
import yaml

class AnsibleManager:
    def __init__(self, sec_mgr):
        self.sec_mgr = sec_mgr

    def run_package_playbook(self, devices, packages, state):
        temp_dir = tempfile.mkdtemp()
        inventory_path = os.path.join(temp_dir, "inventory.ini")
        playbook_path = os.path.join(temp_dir, "playbook.yml")

        with open(inventory_path, "w") as inv_file:
            inv_file.write("[targets]\n")
            for dev in devices:
                dec_cred = self.sec_mgr.decrypt(dev['credential'])
                line = f"{dev['name']} ansible_host={dev['ip']} ansible_port={dev['port']} ansible_user={dev['username']} "
                if dev['auth_type'] == 'password':
                    line += f"ansible_ssh_pass='{dec_cred}' ansible_become_pass='{dec_cred}'\n"
                else:
                    key_path = os.path.join(temp_dir, f"key_{dev['id']}.pem")
                    with open(key_path, "w") as kf:
                        kf.write(dec_cred)
                    os.chmod(key_path, 0o600)
                    line += f"ansible_ssh_private_key_file='{key_path}'\n"
                inv_file.write(line)

        playbook = [{
            'hosts': 'targets',
            'become': True,
            'tasks': [{
                'name': f"Ensure packages are {state}",
                'ansible.builtin.package': {
                    'name': packages,
                    'state': state
                }
            }]
        }]
        
        with open(playbook_path, "w") as pb_file:
            yaml.dump(playbook, pb_file)

        env = os.environ.copy()
        env['ANSIBLE_HOST_KEY_CHECKING'] = 'False'
        
        process = subprocess.Popen(
            ['ansible-playbook', '-i', inventory_path, playbook_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        stdout, stderr = process.communicate()
        
        for f in os.listdir(temp_dir):
            os.remove(os.path.join(temp_dir, f))
        os.rmdir(temp_dir)
        
        return stdout, stderr, process.returncode
