function toEmbedUrl(url) {
    if (!url) return null;
    var yt = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^\&\?\/]+)/);
    if (yt) return 'https://www.youtube.com/embed/' + yt[1];
    var vi = url.match(/vimeo\.com\/(\d+)/);
    if (vi) return 'https://player.vimeo.com/video/' + vi[1];
    return null;
}

contentPanel.querySelectorAll('[data-video-url]').forEach(function (el) {
    var embedUrl = toEmbedUrl(el.dataset.videoUrl);
    if (embedUrl) {
        el.innerHTML = '<iframe src="' + embedUrl + '" allowfullscreen></iframe>';
    }
});
