(function () {
  "use strict";
  const digits = "۰۱۲۳۴۵۶۷۸۹";
  const toFa = value => String(value).replace(/[0-9]/g, d => digits[Number(d)]);
  const toEn = value => String(value || "").replace(/[۰-۹]/g, d => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/[٠-٩]/g, d => "٠١٢٣٤٥٦٧٨٩".indexOf(d));
  const months = ["فروردین","اردیبهشت","خرداد","تیر","مرداد","شهریور","مهر","آبان","آذر","دی","بهمن","اسفند"];
  const weekdays = ["ش","ی","د","س","چ","پ","ج"];

  function g2j(gy, gm, gd) {
    const md = [31,28,31,30,31,30,31,31,30,31,30,31];
    if ((gy%4===0&&gy%100!==0)||gy%400===0) md[1]=29;
    let n=365*(gy-1600)+Math.floor((gy-1600+3)/4)-Math.floor((gy-1600+99)/100)+Math.floor((gy-1600+399)/400);
    for(let i=0;i<gm-1;i++) n+=md[i];
    n+=gd-1; n-=79;
    let jnp=Math.floor(n/12053); n%=12053;
    let jy=979+33*jnp+4*Math.floor(n/1461); n%=1461;
    if(n>=366){jy+=Math.floor((n-1)/365);n=(n-1)%365;}
    return n<186?[jy,1+Math.floor(n/31),1+n%31]:[jy,7+Math.floor((n-186)/30),1+(n-186)%30];
  }
  function j2g(jy,jm,jd) {
    let n=365*(jy-979)+Math.floor((jy-979)/33)*8+Math.floor(((jy-979)%33+3)/4);
    n+=(jm<=6?(jm-1)*31:(jm-7)*30+186)+jd-1+79;
    let gy=1600+400*Math.floor(n/146097); n%=146097; let leap=true;
    if(n>=36525){n--;gy+=100*Math.floor(n/36524);n%=36524;if(n<365)leap=false;else n++;}
    gy+=4*Math.floor(n/1461);n%=1461;
    if(n>=366){leap=false;n--;gy+=Math.floor(n/365);n%=365;}
    const md=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
    let gm=1; while(gm<=12&&n>=md[gm-1]){n-=md[gm-1];gm++;}
    return [gy,gm,n+1];
  }
  function daysInMonth(y,m) {
    if(m<=6) return 31;
    if(m<=11) return 30;
    const g=j2g(y,12,30);
    const back=g2j(g[0],g[1],g[2]);
    return back[0]===y&&back[1]===12&&back[2]===30 ? 30 : 29;
  }
  function readDate(input) {
    const datePart=toEn(input.value.trim().split(/\s+/)[0]).replace(/[-.]/g,"/");
    const p=datePart.split("/").map(Number);
    if(p.length!==3||!p.every(Number.isFinite)||p[0]<1||p[1]<1||p[1]>12||p[2]<1||p[2]>daysInMonth(p[0],p[1])) return null;
    return p;
  }
  function init(input) {
    if(input.dataset.jalaliPickerReady) return;
    input.dataset.jalaliPickerReady="1";
    input.setAttribute("autocomplete","off");
    input.setAttribute("dir","ltr");
    const wrapper=document.createElement("span");
    wrapper.style.cssText="display:inline-flex;align-items:center;gap:5px;position:relative;max-width:100%;";
    input.parentNode.insertBefore(wrapper,input);
    wrapper.appendChild(input);
    const toggle=document.createElement("button");
    toggle.type="button"; toggle.textContent="📅"; toggle.title="انتخاب تاریخ شمسی";
    toggle.style.cssText="cursor:pointer;border:1px solid #aaa;border-radius:5px;padding:5px 8px;background:#fff;";
    wrapper.appendChild(toggle);
    const panel=document.createElement("div");
    panel.hidden=true;
    panel.dir="rtl";
    panel.style.cssText="position:absolute;z-index:99999;top:calc(100% + 5px);right:0;width:280px;max-width:90vw;padding:10px;background:#fff;color:#222;border:1px solid #bbb;border-radius:10px;box-shadow:0 8px 25px #0002;font:14px sans-serif;";
    wrapper.appendChild(panel);
    const header=document.createElement("div");
    header.style.cssText="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;";
    const prev=document.createElement("button"), next=document.createElement("button"), title=document.createElement("strong");
    prev.type=next.type="button"; prev.textContent="‹"; next.textContent="›";
    [prev,next].forEach(b=>b.style.cssText="cursor:pointer;border:1px solid #ddd;background:#f7f7f7;border-radius:5px;padding:2px 10px;font-size:18px;");
    header.append(prev,title,next); panel.appendChild(header);
    const wheels=document.createElement("div");
    wheels.style.cssText="display:grid;grid-template-columns:1fr 1fr 1fr;gap:5px;margin-bottom:8px;";
    function makeSelect(label) {
      const box=document.createElement("label"); box.textContent=label+" ";
      const select=document.createElement("select"); select.style.cssText="width:100%;padding:4px;border:1px solid #ddd;border-radius:5px;background:#fff;";
      box.appendChild(select); wheels.appendChild(box); return select;
    }
    const day=makeSelect("روز"), month=makeSelect("ماه"), year=makeSelect("سال");
    panel.appendChild(wheels);
    const grid=document.createElement("div");
    grid.style.cssText="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px;text-align:center;";
    weekdays.forEach(w=>{const el=document.createElement("span");el.textContent=w;el.style.cssText="font-weight:bold;padding:4px 0;";grid.appendChild(el);});
    panel.appendChild(grid);
    const today=document.createElement("button"); today.type="button"; today.textContent="امروز";
    today.style.cssText="margin-top:8px;width:100%;padding:5px;border:1px solid #ddd;border-radius:5px;background:#f7f7f7;cursor:pointer;";
    panel.appendChild(today);
    const now=new Date(), todayJ=g2j(now.getFullYear(),now.getMonth()+1,now.getDate());
    let current=readDate(input)||todayJ.slice(), view=[current[0],current[1]];
    function fillSelect(select, items, value) {
      select.innerHTML="";
      items.forEach(item=>{const opt=document.createElement("option");opt.value=item.value;opt.textContent=item.label;select.appendChild(opt);});
      select.value=String(value);
    }
    function render() {
      title.textContent=months[view[1]-1]+" "+toFa(view[0]);
      fillSelect(year,Array.from({length:41},(_,i)=>({value:view[0]-20+i,label:toFa(view[0]-20+i)})),current[0]);
      fillSelect(month,months.map((name,i)=>({value:i+1,label:name})),current[1]);
      fillSelect(day,Array.from({length:daysInMonth(view[0],view[1])},(_,i)=>({value:i+1,label:toFa(i+1)})),current[2]);
      while(grid.children.length>7) grid.removeChild(grid.lastChild);
      const first=j2g(view[0],view[1],1);
      const offset=(new Date(first[0],first[1]-1,first[2]).getDay()+1)%7;
      for(let i=0;i<offset;i++) grid.appendChild(document.createElement("span"));
      for(let d=1;d<=daysInMonth(view[0],view[1]);d++) {
        const b=document.createElement("button"); b.type="button"; b.textContent=toFa(d);
        b.style.cssText="padding:6px 0;border:1px solid #eee;border-radius:5px;background:#fff;cursor:pointer;";
        if(view[0]===current[0]&&view[1]===current[1]&&d===current[2]) b.style.cssText+="background:#dceafe;border-color:#6b9be8;font-weight:bold;";
        b.addEventListener("click",()=>{current=[view[0],view[1],d];writeCurrent();});
        grid.appendChild(b);
      }
    }
    function writeCurrent() {
      current[2]=Math.max(1,Math.min(current[2],daysInMonth(current[0],current[1])));
      const dateText=toFa(current[0])+"/"+toFa(String(current[1]).padStart(2,"0"))+"/"+toFa(String(current[2]).padStart(2,"0"));
      const oldTime=toEn(input.value.trim()).match(/\s+(\d{1,2}:\d{2})$/);
      input.value=dateText+(input.name==="scheduled_at"?" "+(oldTime?oldTime[1]:"20:30"):"");
      view=[current[0],current[1]]; render();
      input.dispatchEvent(new Event("input",{bubbles:true}));
      input.dispatchEvent(new Event("change",{bubbles:true}));
    }
    function sync() {
      current=[Number(year.value),Number(month.value),Number(day.value)];
      writeCurrent();
    }
    function show() {
      const parsed=readDate(input);
      if(parsed){current=parsed;view=[parsed[0],parsed[1]];}
      panel.hidden=false;
      panel.style.display="block";
      render();
    }
    function hide() { panel.hidden=true; panel.style.display="none"; }
    toggle.addEventListener("click",event=>{
      event.preventDefault();
      event.stopPropagation();
      if(panel.hidden || panel.style.display==="none") show(); else hide();
    });
    panel.addEventListener("click",event=>event.stopPropagation());
    input.addEventListener("focus",show);
    input.addEventListener("input",()=>{const p=readDate(input);if(p){current=p;view=[p[0],p[1]];render();}});
    prev.addEventListener("click",()=>{view[1]--;if(view[1]<1){view[1]=12;view[0]--;}current=[view[0],view[1],Math.min(current[2],daysInMonth(view[0],view[1]))];render();});
    next.addEventListener("click",()=>{view[1]++;if(view[1]>12){view[1]=1;view[0]++;}current=[view[0],view[1],Math.min(current[2],daysInMonth(view[0],view[1]))];render();});
    [day,month,year].forEach(select=>{
      select.addEventListener("change",sync);
      select.addEventListener("wheel",event=>{event.preventDefault();select.selectedIndex=Math.max(0,Math.min(select.options.length-1,select.selectedIndex+(event.deltaY>0?1:-1)));select.dispatchEvent(new Event("change"));},{passive:false});
    });
    today.addEventListener("click",()=>{current=todayJ.slice();view=[current[0],current[1]];writeCurrent();});
    document.addEventListener("click",event=>{if(!wrapper.contains(event.target))hide();});
    render();
  }
  function boot(){document.querySelectorAll("input.jalali-date-input").forEach(init);}
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",boot); else boot();
})();