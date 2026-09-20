from dataclasses import replace
from copy import deepcopy
from jev_approval.config import Config
from jev_approval.schema import Envelope, CHOICES, HAZARDS
from jev_approval.questions import QUESTION_HASH

POLICY = {'guardian_instructions': 'Allow routine bounded local reads within the trusted user task. Deny unauthorized destructive operations or sensitive disclosure. Unknown evidence requires review.'}

def envelope():
    return Envelope.parse({'schema_version': 1, 'request_id': 'test-request-1', 'source': 'codex-native',
        'action': {'tool': 'exec_command', 'command': ['pwd'], 'cwd': '/workspace'},
        'context': {'policy': POLICY, 'messages': [{'role': 'user', 'text': 'Show the current directory.'}],
                    'authorization_revision': 'revision-1'},
        'guards': {'context_complete': True, 'mandatory_review': False, 'fresh_review': False,
                   'retry': False, 'escalated': False, 'cancelled': False, 'authorization_current': True}})

def raw_response(overrides=None):
    selected = {'risk':'low','authorization':'within_task','evidence':'sufficient','compliance':'compliant'}
    selected.update(overrides or {})
    answers = {k:{'type':'choice','choice':selected[k],
                  'probabilities':{label:1.0 if label==selected[k] else 0.0 for label in labels},
                  'confidence':1.0} for k,labels in CHOICES.items()}
    answers.update({k:{'type':'noul','noul':0.0} for k in HAZARDS})
    return {'model':'jev-1.13.0','answers':answers,'usage':{'input_tokens':100,'output_tokens':20}}

class FakeProvider:
    def __init__(self, raw=None, failure=False):
        self.raw, self.failure, self.calls = raw or raw_response(), failure, 0
        self.states=[]
    def evaluate(self,state):
        self.calls+=1
        self.states.append(deepcopy(state))
        if self.failure:
            raise RuntimeError('private provider traceback must not leak')
        return deepcopy(self.raw)

def config(env=None, **changes):
    env=env or envelope()
    return replace(Config(), mode='enforce',allow_remote_context=True,fast_allow_tools=('exec_command','apply_patch'),
        approved_policy_hashes=(env.policy_hash,),approved_question_hash=QUESTION_HASH,**changes)

def audit_noop(path,record): pass
