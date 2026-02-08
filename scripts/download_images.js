import fs from 'fs';
import https from 'https';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const publicDir = path.join(__dirname, '..', 'public', 'images');

const images = [
  { url: 'https://lh3.googleusercontent.com/aida-public/AB6AXuAjOMs98-V1c_8Kh5AD04Vl0UOYR5AocxaGBhiK7GtoHc5WPbhHPMvO5GIFuji96MIzde90AuXKo_zUEbRgESoslY38gqxWBA53KcW82wxcjAy-pjSzGUk9wWhcQB1bEouUuArBHfANdJU0XBog_XMdsalOQxWIoQyxsjMhmooNPV1wlolEfpFfI0oNzamj_KADBFmJyx_spBcT_9E5ji2T5AVnOU3TN6LButNLhnPNc1sITRI6dIwGm39LAkyjwoGBv6fgrJErt5s', name: 'bg-texture.png' },
  { url: 'https://lh3.googleusercontent.com/aida-public/AB6AXuBSCNdr7OCjBIsYKbrkoOheFNUWtczPsUgGu8lc-AhTRi768Kq43BovZo6cDOG0D7aH1FPsa7gi_4BZRurMU_Tg2b-UlZhAzMkFRuMWrSfXx3btzuyPOuy6ljN1G3-9mhEWO63wE2weKrWlWeKsk_Wh7N97299bOFG-cEobE47BGMiIOAytHE5SPCR8rXpJcel3K3LSIIfN0_W43taJdBwgqrMgSSPWgDJBpVR2nuS-Xl4CcQcoB2CEMgIdvdT6Ku1noKyjPZwQkzg', name: 'prism-logo.png' },
  { url: 'https://lh3.googleusercontent.com/aida-public/AB6AXuB5vwXrWpUSgju3TfIdpp1nBDjCNqwKoTzuNU9JCRbcE2zG779hICJZOWchLD8AtZOXjfycGk5_Ts3_QWYGzAAzQ8PKlStywxbC7a8hXtXihpex8XhqeYCihpcgOFz0Gu634Vhjpns_FCB4tbkV9qVnCmb4KjkBO0rjGHoaNm5SzxPglITzexZMtLpzYOHP6qe_ErPhRbyXWN1RPPGlzP_6YJFmlez666QUjOXfZMIf26Fb-LrZHYpf1Qzpr73jE6qP8-qY3yGM6CM', name: 'user-avatar.png' },
  { url: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDeirVyEaziOhPWIAyj5ml8xbvqaV5lRqjY0uJLqAZOO6_yFNDrolW7Wx257ubKugD7AEPyJih84oxN-AVK27QvSKq-Sl1Ef9XfKqDB1KyEHWPQzRh8L79N5xv9k1fXPFp2KisHeuLYdNxA_OQs6EfkaWwkOf99djIxqzyJ1W0q93TLYa_JDi8UXYBD-lQMolpORTERrUg9y6OYdww7GmcANH9z2tu-SY-7YId12YQt-wfObkBhzrDeLpUw1XLsIMP6t4sLN1Vb20k', name: 'food-fish.png' },
  { url: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDtl43bC4ViIfrKkL3oPclrWrjqwooKu1tbFmC7HKBZCwEc5B5ESM-Fp5dPmtJzMH5tlVTAa28RXuwQU7S2YM-yGyAFKFzXIOlVjABh1ojhzKY7P5l-cVk3z4zcq8fS_ZjQfE1x2GnSCFGVMg2BVdMLZAkb_kJDFmTeWeGTt_zdxZiZWgLXN76NlncmiccaJHmJkhuDzNPSLOe676ozAuqLsWmbHu9POXT4ytJOrCvK5MDvWs8PgMTAslCGmaGcEVdiQbGKI2whHtw', name: 'log-header.png' },
  { url: 'https://placehold.co/600x400.png?text=Menu+Sample', name: 'menu-sample.png' },
  { url: 'https://placehold.co/240x240/12B7F5/ffffff.png?text=QQ', name: 'qq-logo.png' },
  { url: 'https://placehold.co/240x240/07C160/ffffff.png?text=WeChat', name: 'wechat-logo.png' }
];

const downloadImage = (url, filepath) => {
  return new Promise((resolve, reject) => {
    const options = {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      }
    };
    https.get(url, options, (res) => {
      if (res.statusCode === 200) {
        res.pipe(fs.createWriteStream(filepath))
          .on('error', reject)
          .once('close', () => resolve(filepath));
      } else {
        res.resume();
        reject(new Error(`Request Failed With a Status Code: ${res.statusCode}`));
      }
    });
  });
};

const ensureDir = (dir) => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
};

(async () => {
  const publicDir = path.join(__dirname, '..', 'public', 'images');
  ensureDir(publicDir);

  console.log(`Starting download of ${images.length} images to ${publicDir}...`);

  for (const img of images) {
    try {
      const filePath = path.join(publicDir, img.name);
      await downloadImage(img.url, filePath);
      console.log(`✅ Downloaded: ${img.name}`);
    } catch (e) {
      console.error(`❌ Failed to download ${img.name}:`, e.message);
    }
  }

  console.log('All downloads complete.');
})();
