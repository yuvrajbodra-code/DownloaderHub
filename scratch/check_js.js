const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, '..', 'templates', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// Regex to capture script content
const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
let match;
let count = 0;

try {
    while ((match = scriptRegex.exec(html)) !== null) {
        const code = match[1];
        count++;
        // Write script to scratch dir
        const outPath = path.join(__dirname, `script_${count}.js`);
        fs.writeFileSync(outPath, code);
        console.log(`Extracted script #${count} to ${outPath}`);
    }
} catch (e) {
    console.error('Error during extraction:', e);
}
