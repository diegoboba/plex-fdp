select 
    pl.idpedido,
    s.Sucursal,
    p.codplex as IdProducto,
    pl.fecha_desde_comp,
    pl.fecha_hasta_comp,
    sum(FL.Cantidad * 
                    CASE 
                        WHEN FL.TipoCantidad = 'C' THEN P.Unidades 
                        ELSE 1 
                    END
             * 
            CASE 
                WHEN Fl.Tipo = 'NC' THEN -1 
                ELSE 1 
            END
        ) / P.Unidades as venta_pedido
into quantio.ventas_pedido
from quantio.pedidoslineascab pl 
left join quantio.factlineascab fl 
    on pl.sucursal = fl.sucursal
    and pl.IDProducto = fl.idProducto
    and fl.emision_comp between pl.fecha_desde_comp and pl.fecha_hasta_comp
left join quantio.sucursales s 
    on fl.sucursal = s.sucursal
left join quantio.medicamentos p
    on fl.IDProducto = p.CodPlex

where fl.Emision >= dateadd(year, -1, getdate())
and fl.tipo in ('FV', 'TK', 'TF', 'NC', 'ND') 

GROUP BY s.sucursal, pl.idpedido, p.codplex, pl.fecha_desde_comp, pl.fecha_hasta_comp, p.unidades ;

select max(emision) from quantio.factcabecera;
 
drop view quantio.factlineascab;

create view quantio.factlineascab as (
    select 
        fl.*,
        fc.emision,
        fc.tipo,
        fc.sucursal,
        fc.hora,
        DATEADD(MINUTE, DATEDIFF(MINUTE, '00:00:00', fc.hora), 
        DATEADD(HOUR, DATEDIFF(HOUR, '00:00:00', fc.hora), fc.emision)) AS emision_comp
    from quantio.factlineas fl 
    left join quantio.factcabecera fc 
        on fc.IdComprobante = fl.IdComprobante
);
select top 100 * from quantio.factlineascab where cast(emision as date) = '2025-03-15'
;

select top 100 * from quantio.factcabecera where cast(emision as date) = '2025-03-15';
select top 100 * from quantio.plex_pedidos pl 
where pl.fechadesde >= '2025-03-25';

create view quantio.pedidoslineascab as (
    select 
        pl.*,
        p.sucursal,
        DATEADD(MINUTE, DATEDIFF(MINUTE, '00:00:00', p.HoraDesde), 
        DATEADD(HOUR, DATEDIFF(HOUR, '00:00:00', p.HoraDesde), p.FechaDesde)) AS fecha_desde_comp,
        DATEADD(MINUTE, DATEDIFF(MINUTE, '00:00:00', p.HoraHasta), 
        DATEADD(HOUR, DATEDIFF(HOUR, '00:00:00', p.HoraHasta), p.FechaHasta)) AS fecha_hasta_comp
        
    from quantio.plex_pedidoslineas pl 
    left join quantio.plex_pedidos p 
        on pl.IDPedido = p.IDPedido
)