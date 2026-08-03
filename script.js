// Footer year
document.getElementById('year').textContent = new Date().getFullYear();

// ---------------------------------------------------------------
// Replace these with your real Involve Asia deep links once your
// account and brand applications are approved. The keys must match
// the data-platform attribute on each .deal-link in index.html.
// ---------------------------------------------------------------
const affiliateLinks = {
  shopee: 'https://your-involve-asia-link-for-shopee',
  lazada: 'https://your-involve-asia-link-for-lazada',
  foodpanda: 'https://your-involve-asia-link-for-foodpanda'
};

document.querySelectorAll('.deal-link').forEach(link => {
  const platform = link.dataset.platform;
  if (affiliateLinks[platform]) {
    link.href = affiliateLinks[platform];
    link.target = '_blank';
    link.rel = 'noopener sponsored';
  }
});
