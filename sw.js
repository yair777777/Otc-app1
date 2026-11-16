self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {};
  self.registration.showNotification(data.title || 'התראת OTC חמה', {
    body: data.body || 'גיוס גדול / מיזוג / מנכל חדש',
    icon: '/icon.png'
  });
});
