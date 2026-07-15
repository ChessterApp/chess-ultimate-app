#!/usr/bin/env python3
"""Populate Russian and Kazakh translations for courses, modules, lessons."""
from dotenv import load_dotenv
load_dotenv()
import os, json, requests
from supabase import create_client

s = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
OR_KEY = "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"

def translate(text, lang):
    if not text:
        return None
    lang_name = "Russian" if lang == "ru" else "Kazakh (қазақ тілі)"
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", 
        headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"},
        json={
            "model": "deepseek/deepseek-chat",
            "messages": [{"role": "user", "content": f"Translate the following chess-related text to {lang_name}. Keep markdown formatting and chess notation (e4, Nf3, etc) unchanged. Output ONLY the translation, nothing else.\n\n{text}"}],
            "max_tokens": 2000
        }, timeout=30)
    return r.json()["choices"][0]["message"]["content"].strip()

# COURSES
courses = s.table('courses').select('id,title,description').execute().data
for c in courses:
    print(f"Translating course: {c['title']}")
    update = {}
    for lang in ['ru', 'kk']:
        update[f'title_{lang}'] = translate(c['title'], lang)
        update[f'description_{lang}'] = translate(c['description'], lang)
    s.table('courses').update(update).eq('id', c['id']).execute()
    print(f"  Done: {update}")

# MODULES
modules = s.table('modules').select('id,title,description').execute().data
for m in modules:
    print(f"Translating module: {m['title']}")
    update = {}
    for lang in ['ru', 'kk']:
        update[f'title_{lang}'] = translate(m['title'], lang)
        update[f'description_{lang}'] = translate(m['description'], lang)
    s.table('modules').update(update).eq('id', m['id']).execute()
    print(f"  Done: {update}")

# LESSONS
lessons = s.table('lessons').select('id,title,content,hint_text,success_message').execute().data
for l in lessons:
    print(f"Translating lesson: {l['title']}")
    update = {}
    for lang in ['ru', 'kk']:
        update[f'title_{lang}'] = translate(l['title'], lang)
        update[f'content_{lang}'] = translate(l['content'], lang)
        update[f'hint_text_{lang}'] = translate(l['hint_text'], lang)
        update[f'success_message_{lang}'] = translate(l['success_message'], lang)
    s.table('lessons').update(update).eq('id', l['id']).execute()
    print(f"  Done: {l['title']}")

print("\n✅ All translations complete!")
