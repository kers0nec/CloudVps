import docker
import random
import string

client = docker.from_env()

def generate_container_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def create_vps_container(user_id, plan='starter'):
    """Create a Docker container that acts like a VPS"""
    plans = {
        'starter': {'cpu': 0.5, 'memory': '512m', 'storage': '10g'},
        'standard': {'cpu': 1.0, 'memory': '1g', 'storage': '20g'},
        'performance': {'cpu': 2.0, 'memory': '2g', 'storage': '40g'},
    }
    
    config = plans.get(plan, plans['starter'])
    container_name = f"vps-{user_id}-{generate_container_id()}"
    
    try:
        container = client.containers.create(
            image='ubuntu:22.04',
            name=container_name,
            command='sleep infinity',
            host_config=client.api.create_host_config(
                cpu_shares=int(config['cpu'] * 1024),
                mem_limit=config['memory'],
                storage_opt={'size': config['storage']}
            ),
            labels={'user_id': str(user_id), 'plan': plan}
        )
        container.start()
        return {
            'id': container.id[:12],
            'name': container_name,
            'status': container.status,
            'plan': plan,
            'cpu': config['cpu'],
            'memory': config['memory'],
            'storage': config['storage']
        }
    except Exception as e:
        return {'error': str(e)}

def get_user_containers(user_id):
    """Get all containers owned by a user"""
    containers = client.containers.list(all=True, filters={'label': f'user_id={user_id}'})
    result = []
    for c in containers:
        labels = c.labels
        result.append({
            'id': c.id[:12],
            'name': c.name,
            'status': c.status,
            'plan': labels.get('plan', 'starter'),
            'created': c.attrs['Created']
        })
    return result

def stop_container(container_id):
    """Stop a container"""
    try:
        container = client.containers.get(container_id)
        container.stop()
        return {'success': True}
    except Exception as e:
        return {'error': str(e)}

def start_container(container_id):
    """Start a container"""
    try:
        container = client.containers.get(container_id)
        container.start()
        return {'success': True}
    except Exception as e:
        return {'error': str(e)}

def delete_container(container_id):
    """Delete a container"""
    try:
        container = client.containers.get(container_id)
        container.remove(force=True)
        return {'success': True}
    except Exception as e:
        return {'error': str(e)}
