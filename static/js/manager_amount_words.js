(function () {
  const ONES=["صفر","یک","دو","سه","چهار","پنج","شش","هفت","هشت","نه","ده","یازده","دوازده","سیزده","چهارده","پانزده","شانزده","هفده","هجده","نوزده"];
  const TENS=["","","بیست","سی","چهل","پنجاه","شصت","هفتاد","هشتاد","نود"];
  const HUNDREDS=["","صد","دویست","سیصد","چهارصد","پانصد","ششصد","هفتصد","هشتصد","نهصد"];
  const SCALES=["","هزار","میلیون","میلیارد","تریلیون","کوادریلیون"];
  function words(v){
    let s=String(v||"").replace(/[,٬\s]/g,"").replace(/[۰-۹]/g,d=>"۰۱۲۳۴۵۶۷۸۹".indexOf(d));
    if(!s)return "";
    let n=Math.trunc(Number(s)); if(!Number.isFinite(n))return "";
    if(n===0)return "صفر تومان";
    if(n<0)return "منفی "+words(-n);
    const out=[]; let scale=0;
    while(n){const p=n%1000;if(p){const h=Math.floor(p/100),r=p%100,a=[];
      if(h)a.push(HUNDREDS[h]); if(r<20&&r)a.push(ONES[r]); else if(r){a.push(TENS[Math.floor(r/10)]);if(r%10)a.push(ONES[r%10]);}
      let t=a.join(" و ");if(scale)t+=" "+SCALES[scale];out.unshift(t);}
      n=Math.floor(n/1000);scale++;}
    return out.join(" و ")+" تومان";
  }
  function add(input){
    if(input.dataset.wordsBound)return;
    input.dataset.wordsBound="1";
    const box=document.createElement("div");
    box.className="amount-words-live";
    box.setAttribute("aria-live","polite");
    input.parentNode.appendChild(box);
    const update=()=>box.textContent=input.value?"مبلغ به حروف: "+words(input.value):"";
    input.addEventListener("input",update); input.addEventListener("change",update); update();
  }
  document.addEventListener("DOMContentLoaded",function(){document.querySelectorAll(".amount-input").forEach(add);});
})();