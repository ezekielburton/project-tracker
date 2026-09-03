from app.modules.core.shared.extensions import db
from datetime import datetime


class BlogPost(db.Model):
    __tablename__ = 'blog_posts'

    id            = db.Column(db.Integer, primary_key=True)
    title         = db.Column(db.String(200), nullable=False)
    version_tag   = db.Column(db.String(80))
    author_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_published  = db.Column(db.Boolean, nullable=False, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    published_at  = db.Column(db.DateTime)
    sections_json = db.Column(db.Text, nullable=False, default='[]')

    author = db.relationship('User', backref='blog_posts')

    def sections(self):
        import json
        data = json.loads(self.sections_json or '[]')
        return [_BlogSection(s) for s in data]

    def __repr__(self):
        return f'<BlogPost {self.title}>'


class _BlogSection:
    def __init__(self, d):
        self.anchor = d.get('anchor', '')
        self.number = d.get('number', '')
        self.title  = d.get('title', '')
        self.blocks = [_BlogBlock(b) for b in d.get('blocks', [])]


class _BlogBlock:
    def __init__(self, d):
        self.type  = d.get('type', 'body')
        self.text  = d.get('text', '')
        self.color = d.get('color')
        self.items = d.get('items', [])
        self.url   = d.get('url', '')


class BlogComment(db.Model):
    __tablename__ = 'blog_comments'

    id         = db.Column(db.Integer, primary_key=True)
    post_id    = db.Column(db.Integer, db.ForeignKey('blog_posts.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id  = db.Column(db.Integer, db.ForeignKey('blog_comments.id'), nullable=True)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    author  = db.relationship('User', backref='blog_comments')
    replies = db.relationship(
        'BlogComment',
        foreign_keys='BlogComment.parent_id',
        backref=db.backref('parent', remote_side='BlogComment.id'),
        lazy='select'
    )

    def __repr__(self):
        return f'<BlogComment {self.id} on post {self.post_id}>'
