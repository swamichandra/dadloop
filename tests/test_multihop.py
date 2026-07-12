"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests multi-hop dependent tool reasoning across sequential calls."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.core import tools as tk

# Fake model that reasons across results: it checks pantry, SEES it's empty,
# THEREFORE checks budget, SEES it's tight, THEREFORE decides. Multi-hop:
# each call is chosen based on the previous tool_result the model just saw.
class FakeMessages:
    def __init__(self): self.step = 0; self.saw = []
    def create(self, **kw):
        # record what tool results the model can see so far
        for m in kw['messages']:
            if isinstance(m.get('content'), list):
                for b in m['content']:
                    if isinstance(b, dict) and b.get('type')=='tool_result':
                        self.saw.append(b['content'])
        self.step += 1
        if self.step == 1:
            return NS(content=[NS(type='tool_use', id='a', name='check_pantry', input={})])
        if self.step == 2:
            # decision depends on pantry result being 'empty'
            assert any('bare' in s for s in self.saw), 'model did not see pantry result'
            return NS(content=[NS(type='tool_use', id='b', name='check_wallet',
                                  input={'amount': 60, 'reason': 'veggies for 8'})])
        if self.step == 3:
            # decision depends on wallet saying NO (60 > 40 budget)
            assert any('NO' in s for s in self.saw), 'model did not see budget rejection'
            return NS(content=[NS(type='tool_use', id='c', name='web_search',
                                  input={'query': 'cheap vegetarian skewer recipe for 8'})])
        # final synthesis
        return NS(content=[NS(type='text',
            text="Pantry's empty and $60 blows the $40 budget, so here's a cheaper skewer plan.")])
class FakeClient:
    def __init__(self): self.messages = FakeMessages()

tmp = Path(tempfile.mkdtemp())/'mem'
tk.WORLD.update(pantry_has_veggies=False, budget=40, propane='full')
dad = AgentLoop(Context(memory=SemanticMemory(tmp)))
dad._client = FakeClient()

# stub web_search so we don't need real network in the test
tk._TOOLS['web_search'] = (tk._TOOLS['web_search'][0],
    lambda ctx, query: "Found: grilled veggie skewers ~$3.50/head. Peppers, zucchini, onion.")

hops = []
dad.turn("feed 8 people veggie skewers, can we afford it?",
         on_event=lambda k,p: hops.append((k,p[0] if k in('tool_call','tool_result') else p)))

calls = [p for k,p in hops if k=='tool_call']
print('tool call chain:', calls)
assert calls == ['check_pantry','check_wallet','web_search'], calls
print('\nPASS: 3 dependent hops — each chosen from the previous result.')
print('      pantry empty → check budget → over budget → search cheaper recipe')
