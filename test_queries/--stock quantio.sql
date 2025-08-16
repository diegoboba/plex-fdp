drop view quantio.stock_quantio

--stock quantio
create view [quantio].[stock_quantio] as 
select 
    p.IDProducto,
    p.codebar,
    p.activo,
    p.visible,
    coalesce(sum(sl.cantidad),0) as Stock_Quantio
from quantio.productos p 
left join quantio.stocklotes sl
    on p.IDProducto = sl.IDProducto
    and sl.IdDeposito = 1
    and (FORMAT(sl.FechaVencimiento, 'yyyyMM') >= FORMAT(GETDATE(), 'yyyyMM'))

group by p.IDProducto, p.codebar, p.activo,
    p.visible
;
select top 100 * from quantio.stock_quantio ;
select top 100 * from quantio.productos p 
;
drop view quantio.stock_quantio_sucursales
;
--stock quantio & sucursales
create view [quantio].[stock_quantio_sucursales] as 
select 
    q.IDProducto,
    q.codebar,
    q.activo as activo_q,
    q.visible as visible_q,
    s.nombrefantasia as Sucursal,
    st.Cantidad as stock_sucursal,
    q.Stock_Quantio,
    m.activo as activo_m,
    m.visible as visible_m
from quantio.stock_quantio q 
left join quantio.plex_stock st 
    on q.IDProducto = st.IDProducto
left join quantio.sucursales s 
    on st.Sucursal = s.Sucursal
left join quantio.medicamentos m
    on m.CodPlex = q.IDProducto

;

select top 100 * from quantio.stock_quantio_sucursales;

select top 1000 * from plex.clientes
where CodCliente in (30882,
13224,
9744,
22443,
25051,
25051,
25051,
13699,
25051,
22369,
1410016859,
39651)
;

select distinct CliApeNom from plex.factcabecera 
where IDCliente = 9744
