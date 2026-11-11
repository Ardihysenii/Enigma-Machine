"""Task-first dark portal layout checks, without a live database."""
from pathlib import Path
from html.parser import HTMLParser
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Layout(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.section = None
        self.locations = {}
        self.ids = []
        self.stack = []
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        identifier = attrs.get('id')
        if tag == 'section':
            self.stack.append(self.section)
            self.section = identifier or self.section
        if identifier:
            self.ids.append(identifier)
            self.locations[identifier] = self.section
    def handle_endtag(self, tag):
        if tag == 'section' and self.stack:
            self.section = self.stack.pop()

class PortalDesignTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / 'templates/portal.html').read_text(encoding='utf-8')
        self.layout = Layout(self.html)
    def test_no_duplicate_ids(self):
        self.assertEqual(len(self.layout.ids), len(set(self.layout.ids)))
    def test_students_are_separate_from_grade_entry(self):
        self.assertEqual(self.layout.locations['teacher-directory-body'], 'teacher-directory')
        self.assertEqual(self.layout.locations['teacher-enrollment-form'], 'students-view')
        self.assertEqual(self.layout.locations['records-body'], 'records-view')
    def test_course_setup_is_on_courses_page(self):
        self.assertEqual(self.layout.locations['teacher-course-form'], 'courses-view')
        self.assertEqual(self.layout.locations['teacher-assignment-form'], 'courses-view')
    def test_security_demo_remains_available_without_large_banner(self):
        self.assertIn('demo-settings', self.html)
        self.assertIn('id="policy-controls"', self.html)
        self.assertIn('id="test-professor"', self.html)
        self.assertNotIn('class="demo-banner"', self.html)
    def test_dark_theme_is_preserved(self):
        css = (ROOT / 'static/portal.css').read_text(encoding='utf-8')
        self.assertIn('color-scheme: dark', css)
        self.assertIn('--bg:#101113', css)
        self.assertIn('--gold:#d6b77e', css)

if __name__ == '__main__':
    unittest.main()
