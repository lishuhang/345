    // /ysp<type><idx>.m3u8  (e.g. /yspc01.m3u8, /yspw03.m3u8)
    const yspM3u8Match = path.match(/^\/(ysp[cw]\d+)\.m3u8$/);
    if (yspM3u8Match) {
      return handleYspM3u8(yspM3u8Match[1], request);
    }

    // /yseg/<yspKey>/<filename>  (YSP segment proxy)
    const ysegMatch = path.match(/^\/yseg\/(ysp[cw]\d+)\/(.+)$/);
    if (ysegMatch) {
      return handleYseg(ysegMatch[1], ysegMatch[2], request);
    }

    // /<tid><id>.m3u8  (e.g. /gt5.m3u8)
    const m3u8Match = path.match(/^\/(\w+?)(\d+)\.m3u8$/);
    if (m3u8Match) {
      return handleM3u8(m3u8Match[1], parseInt(m3u8Match[2], 10), request);
    }
