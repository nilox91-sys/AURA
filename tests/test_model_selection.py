import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import test_app as base
import test_integrations as integration
from ai_engine import LLMEngine,ProviderState
from settings_store import SettingsManager

MODEL='gemini:gemini-3.1-flash-lite'


class ModelSelectionTests(unittest.TestCase):
    setUp=base.JarvisTests.setUp

    def enable_selection(self):
        base.jarvis.settings_manager.update({'model':MODEL,'ai_model_allowlist':[MODEL],
            'gemini_api_key':'google-secret','hf_api_key':'voice-secret','groq_api_key':'other-secret'})

    def test_only_selected_models_appear_in_pages_and_provider_api(self):
        self.enable_selection()
        data=self.client.get('/api/providers').json
        self.assertEqual([(p['id'],p['models']) for p in data['providers']],[('gemini',['gemini-3.1-flash-lite'])])
        page=self.client.get('/settings').get_data(as_text=True)
        self.assertIn('<select id="model-id">',page)
        self.assertNotIn('<option value="openrouter">',page)
        self.assertNotIn('<option value="auto">',page)
        self.assertNotIn('id="allow-fallback"',page)
        self.assertIn('Token Hugging Face · voce Irodori',page)
        self.assertEqual(page.count('id="hf-api-key"'),1)
        for secret in ('google-secret','voice-secret','other-secret'):self.assertNotIn(secret,page)
        self.assertEqual([p['id'] for p in self.client.get('/api/status').json['ai_health']],['gemini'])

    def test_backend_rejects_removed_model_and_preserves_all_saved_keys(self):
        self.enable_selection()
        response=self.client.post('/api/save_settings',json={'model':'openrouter:openrouter/free','gemini_api_key':'replaced'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(base.jarvis.settings_manager.get('gemini_api_key'),'google-secret')
        self.assertEqual(base.jarvis.settings_manager.get('hf_api_key'),'voice-secret')
        self.assertEqual(self.client.post('/api/connect/openrouter',json={'key':'another-secret-key'}).status_code,400)
        self.assertEqual(self.client.post('/api/save_settings',json={'allow_fallback':True}).status_code,200)
        self.assertFalse(base.jarvis.settings_manager.get('allow_fallback'))

    def test_routing_never_tries_removed_models_or_providers(self):
        self.enable_selection();settings=base.jarvis.settings_manager.get_all()
        settings['allow_fallback']=True
        self.assertEqual(LLMEngine.provider_candidates(MODEL,settings),[('gemini','gemini-3.1-flash-lite')])
        for other in ('auto:free','gemini:gemini-3.8-flash','groq:openai/gpt-oss-20b'):
            self.assertEqual(LLMEngine.provider_candidates(other,settings),[])
        with patch('ai_engine.call_extra') as call:
            with self.assertRaises(ValueError):LLMEngine.call_provider('openai','gpt-4.1-mini',[],settings)
        call.assert_not_called()

    def test_allowlist_is_validated_and_copies_cannot_mutate_it(self):
        self.enable_selection();manager=base.jarvis.settings_manager
        for bad in ('gemini:one',[None],['unknown:one'],['gemini:bad model'],['gemini:one']*65):
            with self.assertRaises(ValueError):manager.update({'ai_model_allowlist':bad})
        copy=manager.get('ai_model_allowlist');copy.clear()
        copy=manager.get_all();copy['ai_model_allowlist'].clear()
        self.assertEqual(manager.get('ai_model_allowlist'),[MODEL])
        loaded=SettingsManager(manager.filepath,base.jarvis.DEFAULT_SETTINGS)
        self.assertEqual(loaded.get('ai_model_allowlist'),[MODEL])


class SelectionApiTests(unittest.TestCase):
    setUp=integration.IntegrationTests.setUp

    def test_catalog_is_filtered_and_removed_probes_do_not_send_requests(self):
        self.manager.update({'model':MODEL,'ai_model_allowlist':[MODEL],'gemini_api_key':'secret'})
        with patch.object(LLMEngine,'health',ProviderState()),patch('settings_api.discover',return_value={
            'id':'gemini','state':'available','models':['gemini-3.1-flash-lite','gemini-2.5-flash','gemini-3.8-flash'],'message':'raw'}):
            response=self.client.post('/api/integrations/check',json={'provider':'gemini'})
        self.assertEqual(response.json['models'],['gemini-3.1-flash-lite'])
        with patch('settings_api.discover') as discover,patch.object(LLMEngine,'call_provider') as generate:
            self.assertEqual(self.client.post('/api/integrations/check',json={'provider':'groq'}).status_code,400)
            self.assertEqual(self.client.post('/api/integrations/test',json={'provider':'gemini','model':'gemini-3.8-flash'}).status_code,400)
        discover.assert_not_called();generate.assert_not_called()
        self.assertNotIn('ai_model_allowlist',self.client.get('/api/preferences/export').json['preferences'])

if __name__=='__main__':unittest.main()
