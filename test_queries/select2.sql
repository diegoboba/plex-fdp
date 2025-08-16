    select 
        *

    from plex.factcabecera fc 
    left join plex.factlineas fl 
        on fc.IDComprobante = fl.IDComprobante
    left join plex.sucursales s 
        on fc.Sucursal = s.Sucursal
    left join plex.medicamentos m 
        on fl.IDProducto = m.codplex
    where cast(fc.emision as date) >= GETDATE() - 2
    and s.NombreFantasia = 'COLON'
    and m.codplex = '1010306501'