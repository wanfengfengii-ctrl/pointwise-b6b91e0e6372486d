from exact import rational, required_text
from issue.evidence import FrozenEvidence


def stop_body(batch_id: str, commands, evidence: FrozenEvidence) -> dict:
    batch = required_text(batch_id, 'batch_id')
    if not isinstance(commands, (list, tuple)):
        raise ValueError('stop commands must be a list or tuple')
    rows = []
    seen = set()
    for row in commands:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('a stop command row requires a command ID and a time')
        command_id = required_text(row[0], 'command_id')
        if command_id in seen:
            raise ValueError(f'duplicate stop command: {command_id}')
        seen.add(command_id)
        moment = rational(row[1], 'command time')
        rows.append([command_id, str(moment)])
    return {
        'batch_id': batch,
        'commands': rows,
        'affine': [[str(value) for value in affine] for affine in evidence.affine_rows],
    }
