"""Real RSA-PSS plus teacher-only API/CSRF contracts, no production database."""
import copy
import unittest
from unittest.mock import patch, MagicMock
import app as web
import teacher_signatures as signing


def payload():
    return dict(version=1, document='College notice: exam at 10:00. Café.', drawing=[[[10,20],[30,40],[80,35]]])


class TeacherSignatureTests(unittest.TestCase):
    def setUp(self):
        web.app.config.update(TESTING=True, CLOUD_DEMO=False)
        self.client=web.app.test_client()
        self.csrf='a'*43
        self.client.set_cookie('enigma_portal_csrf',self.csrf)
        self.actor=dict(id='teacher-id',name='Fictional Teacher',email='teacher@test.invalid',role='professor')
        self.db=patch('portal.database');self.db.start().return_value.__enter__.return_value=MagicMock()
        self.current=patch('portal.current_actor',side_effect=lambda *a,**k:self.actor);self.current.start()
        patch('portal.audit').start()
        self.addCleanup(patch.stopall)
    def post(self,route,data,csrf=True):
        return self.client.post('/api/portal/signatures/'+route,json=data,headers={'X-CSRF-Token':self.csrf} if csrf else {})
    def signed(self):
        r=self.post('sign',{'payload':payload()});self.assertEqual(r.status_code,200,r.json);return r.json
    def verify(self,bundle,content=None,test='normal'):
        return self.post('verify',dict(payload=content if content is not None else bundle['payload'],signature=bundle['signature'],publicKey=bundle['publicKey'],test=test))
    def test_original_modified_text_modified_drawing_and_wrong_key(self):
        b=self.signed()
        self.assertTrue(self.verify(b).json['verified'])
        changed=copy.deepcopy(b['payload']);changed['document']=changed['document'].replace('10:00','12:00')
        self.assertFalse(self.verify(b,changed).json['verified'])
        changed=copy.deepcopy(b['payload']);changed['drawing'][0][0][0]+=1
        self.assertFalse(self.verify(b,changed).json['verified'])
        changed=copy.deepcopy(b['payload']);changed['drawing']=[]
        self.assertFalse(self.verify(b,changed).json['verified'])
        self.assertFalse(self.verify(b,test='wrong_key').json['verified'])
        self.assertTrue(self.verify(b).json['verified'])
        self.assertFalse(self.verify(b).json['identityTrusted'])
        self.assertNotIn('PRIVATE KEY',str(b));self.assertNotIn('privateKey',b)
    def test_normalized_coordinates_and_fresh_keys(self):
        b=self.signed();c=copy.deepcopy(b['payload']);c['drawing']=[[[float(x),float(y)] for x,y in c['drawing'][0]]]
        self.assertTrue(self.verify(b,c).json['verified'])
        other=self.signed();self.assertNotEqual(b['publicKey'],other['publicKey'])
    def test_only_professors_can_sign_or_verify_even_when_controls_are_disabled(self):
        b=self.signed()
        for role,expected in [('student',403),('admin',403),(None,401)]:
            self.actor=dict(self.actor,role=role) if role else None
            with patch('portal.policy',return_value={'rules':{}}):
                self.assertEqual(self.post('sign',{'payload':payload()}).status_code,expected)
                self.assertEqual(self.verify(b).status_code,expected)
                r=self.client.post('/api/tasks/signatures/run',json={'message':'Notice'},headers={'X-CSRF-Token':self.csrf})
                self.assertEqual(r.status_code,expected)
    def test_csrf_required_for_new_and_legacy_signing(self):
        self.assertEqual(self.post('sign',{'payload':payload()},csrf=False).status_code,403)
        self.assertEqual(self.client.post('/api/tasks/signatures/run',json={'message':'Notice'}).status_code,403)
    def test_invalid_input_is_rejected(self):
        for field,value in [('document',''),('document',chr(0xd800)),('drawing',[]),('drawing',[[[True,5],[10,10]]]),('drawing',[[[-1,0],[10,10]]]),('drawing',[[[float('nan'),0],[10,10]]])]:
            p=payload();p[field]=value
            self.assertEqual(self.post('sign',{'payload':p}).status_code,400)
        b=self.signed()
        self.assertEqual(self.post('verify',dict(payload=b['payload'],publicKey='bad',signature=b['signature'],test='normal')).status_code,400)
    def test_legacy_teacher_round_trip_still_works(self):
        r=self.client.post('/api/tasks/signatures/run',json={'message':'Notice'},headers={'X-CSRF-Token':self.csrf})
        self.assertEqual(r.status_code,200,r.json);self.assertTrue(r.json['original_verified'])

    def test_workspace_and_assets_render_without_changing_rsa(self):
        page=self.client.get('/')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'id="cn-pad"',page.data)
        self.assertIn(b'id="rsa-demo"',page.data)
        for path in ('/static/course-notices.js','/static/course-notices.css'):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code,200)
        self.assertIn(b'id="teacher-signature-link"',self.client.get('/college').data)
